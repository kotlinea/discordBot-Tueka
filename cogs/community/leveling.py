"""Independent text and voice leveling with cumulative role rewards."""
import random
import time

import discord
from discord import app_commands
from discord.ext import commands, tasks

from community import CommunityRepository
from guild_settings import GuildSettingsRepository


MAX_REWARDS = 25


def calculate_level(xp: int) -> tuple[int, int]:
    level = 0
    while xp >= required_xp(level):
        xp -= required_xp(level)
        level += 1
    return level, xp


def required_xp(level: int) -> int:
    return 5 * level**2 + 50 * level + 100


class LevelingCog(commands.Cog):
    help_category = 'レベリング'
    help_module = 'leveling'

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.repository = CommunityRepository(bot.settings.database_url)
        self.guild_settings = GuildSettingsRepository(bot.settings.database_url)
        self.last_xp_time: dict[tuple[int, int], float] = {}
        self.voice_xp_tick.start()

    def cog_unload(self) -> None:
        self.voice_xp_tick.cancel()

    async def _notify(self, guild: discord.Guild, channel_id: int | None, member: discord.Member, level: int, track: str) -> None:
        channel = guild.get_channel(int(channel_id)) if channel_id else None
        if isinstance(channel, discord.TextChannel):
            label = "VC" if track == "voice" else "テキスト"
            await channel.send(f"🎉 {member.mention} が{label}レベルアップ！ **Lv {level}**", allowed_mentions=discord.AllowedMentions(users=[member], everyone=False, roles=False))

    async def _grant_rewards(self, member: discord.Member, level: int, rewards: list[dict]) -> None:
        me = member.guild.me
        if me is None:
            return
        for reward in rewards[:MAX_REWARDS]:
            try:
                required_level, role_id = int(reward["level"]), int(reward["role_id"])
            except (KeyError, TypeError, ValueError):
                continue
            if required_level > level:
                continue
            role = member.guild.get_role(role_id)
            if role is None or role.managed or role.is_default() or role >= me.top_role or role in member.roles:
                continue
            try:
                await member.add_roles(role, reason=f"Level reward at level {level}")
            except discord.HTTPException:
                continue

    async def _on_level_up(self, member: discord.Member, level: int, settings: dict, track: str) -> None:
        prefix = "voice" if track == "voice" else "text"
        await self._grant_rewards(member, level, settings.get(f"{prefix}_role_rewards", []))
        await self._notify(member.guild, settings.get(f"{prefix}_notification_channel_id"), member, level, track)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None or not isinstance(message.author, discord.Member):
            return
        key = (message.guild.id, message.author.id)
        now = time.monotonic()
        last = self.last_xp_time.get(key)
        if last is not None and now - last < 60:
            return
        module = self.guild_settings.get_module(message.guild.id, "leveling")
        if not module["enabled"]:
            return
        amount = random.randint(15, 25)
        user = self.repository.add_xp(message.guild.id, message.author.id, amount)
        old_level, _ = calculate_level(user["xp"] - amount)
        new_level, _ = calculate_level(user["xp"])
        self.last_xp_time[key] = now
        if new_level > old_level:
            await self._on_level_up(message.author, new_level, module["settings"], "text")

    @tasks.loop(seconds=60)
    async def voice_xp_tick(self) -> None:
        now = time.monotonic()
        self.last_xp_time = {key: last for key, last in self.last_xp_time.items() if now - last < 60}
        for guild_id in self.guild_settings.enabled_module_guild_ids("leveling"):
            guild = self.bot.get_guild(guild_id)
            if guild is None:
                continue
            module = self.guild_settings.get_module(guild_id, "leveling")
            settings = module["settings"]
            if not module["enabled"] or not settings.get("voice_enabled"):
                continue
            amount = max(1, min(int(settings.get("voice_xp_per_minute", 5)), 100))
            allow_solo = bool(settings.get("voice_allow_solo"))
            allow_muted = bool(settings.get("voice_allow_muted"))
            for channel in guild.voice_channels:
                if guild.afk_channel and channel.id == guild.afk_channel.id:
                    continue
                humans = [member for member in channel.members if not member.bot]
                if not allow_solo and len(humans) < 2:
                    continue
                for member in humans:
                    state = member.voice
                    if state is None or (not allow_muted and (state.self_mute or state.mute or state.self_deaf or state.deaf)):
                        continue
                    current = self.repository.add_voice_xp(guild.id, member.id, amount)
                    old_level, _ = calculate_level(current["xp"] - amount)
                    new_level, _ = calculate_level(current["xp"])
                    if new_level > old_level:
                        await self._on_level_up(member, new_level, settings, "voice")

    @voice_xp_tick.before_loop
    async def before_voice_xp_tick(self) -> None:
        await self.bot.wait_until_ready()

    async def _require_enabled(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None or not self.guild_settings.module_enabled(interaction.guild.id, "leveling"):
            await interaction.response.send_message("この機能は管理者により無効です。", ephemeral=True)
            return False
        return True

    @app_commands.command(description="現在のテキストレベルを確認します。")
    @app_commands.guild_only()
    async def rank(self, interaction: discord.Interaction) -> None:
        if not await self._require_enabled(interaction):
            return
        assert interaction.guild is not None
        xp = self.repository.get_user(interaction.guild.id, interaction.user.id)["xp"]
        level, progress = calculate_level(xp)
        await interaction.response.send_message(f"📊 {interaction.user.mention} のテキストレベル: **Lv {level}**\n現在のXP: {progress} / {required_xp(level)}")

    @app_commands.command(description="テキストXPランキングを表示します。")
    @app_commands.guild_only()
    async def leaderboard(self, interaction: discord.Interaction) -> None:
        if not await self._require_enabled(interaction):
            return
        assert interaction.guild is not None
        ranked = self.repository.leaderboard(interaction.guild.id)
        if not ranked:
            await interaction.response.send_message("まだテキストXPデータがありません。")
            return
        lines = [f"**{i}.** <@{data['user_id']}> - {data['xp']} XP (Lv.{calculate_level(data['xp'])[0]})" for i, data in enumerate(ranked, 1)]
        await interaction.response.send_message("🏆 **テキストXPランキング** 🏆\n" + "\n".join(lines))

    @app_commands.command(description="現在のVCレベルを確認します。")
    @app_commands.guild_only()
    async def vcrank(self, interaction: discord.Interaction) -> None:
        if not await self._require_enabled(interaction):
            return
        assert interaction.guild is not None
        xp = self.repository.get_voice_user(interaction.guild.id, interaction.user.id)["xp"]
        level, progress = calculate_level(xp)
        await interaction.response.send_message(f"🎙️ {interaction.user.mention} のVCレベル: **Lv {level}**\n現在のXP: {progress} / {required_xp(level)}")

    @app_commands.command(description="VC XPランキングを表示します。")
    @app_commands.guild_only()
    async def vcleaderboard(self, interaction: discord.Interaction) -> None:
        if not await self._require_enabled(interaction):
            return
        assert interaction.guild is not None
        ranked = self.repository.voice_leaderboard(interaction.guild.id)
        if not ranked:
            await interaction.response.send_message("まだVC XPデータがありません。")
            return
        lines = [f"**{i}.** <@{data['user_id']}> - {data['xp']} XP (Lv.{calculate_level(data['xp'])[0]})" for i, data in enumerate(ranked, 1)]
        await interaction.response.send_message("🎙️ **VC XPランキング** 🎙️\n" + "\n".join(lines))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(LevelingCog(bot))
