"""Administrator-only, observation-only trust score module."""
import discord
from discord import app_commands
from discord.ext import commands, tasks

from moderation import ModerationRepository
from guild_settings import GuildSettingsRepository


class TrustCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.moderation_repository = ModerationRepository(bot.settings.database_url)
        self.guild_settings = GuildSettingsRepository(bot.settings.database_url)
        self.purge_expired_data.start()

    def cog_unload(self) -> None:
        self.purge_expired_data.cancel()

    async def _enabled(self, interaction: discord.Interaction) -> bool:
        if interaction.guild is None or not self.guild_settings.module_enabled(interaction.guild.id, "trust_score"):
            await interaction.response.send_message("この機能は管理者により無効です。", ephemeral=True)
            return False
        return True

    @app_commands.command(description="メンバーの信頼度スコアと算出理由を表示します。")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def trust_score(self, interaction: discord.Interaction, member: discord.Member) -> None:
        if not await self._enabled(interaction):
            return
        assert interaction.guild is not None
        settings = self.guild_settings.get_module(interaction.guild.id, "trust_score")["settings"]
        retention_days = max(1, min(int(settings.get("trust_retention_days", 90)), 3650))
        threshold = max(0, min(int(settings.get("trust_flag_threshold", 60)), 100))
        result = self.moderation_repository.trust_score(interaction.guild.id, member.id, retention_days)
        embed = discord.Embed(title=f"{member.display_name} の信頼度", description=f"**{result['score']} / 100**" + (" ⚠️ 要確認" if result["score"] <= threshold else ""), color=discord.Color.orange() if result["score"] <= threshold else discord.Color.green())
        embed.set_footer(text=f"保持期間: {retention_days}日。これは管理者向けの表示のみで、自動制裁は行いません。")
        if result["events"]:
            lines = [f"• {event['category']}: {event['weight']} ({event['reason'] or '理由なし'})" for event in result["events"][:10]]
            reasons = "\n".join(lines)
            if len(reasons) > 1024:
                reasons = reasons[:1023] + "…"
            embed.add_field(name="算出理由", value=reasons, inline=False)
        else:
            embed.add_field(name="算出理由", value="保持期間内に記録された違反はありません。", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(description="メンバーの信頼度イベントを手動で解除します。制裁履歴は残ります。")
    @app_commands.checks.has_permissions(manage_guild=True)
    @app_commands.guild_only()
    async def clear_trust_score(self, interaction: discord.Interaction, member: discord.Member) -> None:
        if not await self._enabled(interaction):
            return
        assert interaction.guild is not None
        self.moderation_repository.clear_trust_events(interaction.guild.id, member.id)
        await interaction.response.send_message(f"{member.mention} の信頼度イベントを解除しました。制裁履歴は削除していません。", ephemeral=True)

    @tasks.loop(hours=24)
    async def purge_expired_data(self) -> None:
        for guild_id in self.guild_settings.enabled_module_guild_ids("trust_score"):
            settings = self.guild_settings.get_module(guild_id, "trust_score")["settings"]
            self.moderation_repository.purge_trust_events(guild_id, int(settings.get("trust_retention_days", 90)))

    @purge_expired_data.before_loop
    async def before_purge_expired_data(self) -> None:
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(TrustCog(bot))
