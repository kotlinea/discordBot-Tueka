"""Guild-scoped safety modules: moderation, filtering and spam."""
import asyncio
import hashlib
import logging
import re
import time
from collections import defaultdict, deque
from datetime import timedelta

import discord
import httpx
from discord import app_commands
from discord.ext import commands

from storage import GuildStorage
from automod.service import ModerationService


MAX_TIMEOUT = 28 * 24 * 60
URL_RE = re.compile(r"https?://[^\s<>]+", re.I)
LOGGER = logging.getLogger(__name__)


class SafetyCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot, self.storage = bot, GuildStorage(bot.settings.database_path)
        self.moderation = ModerationService(bot, self.storage)
        self.recent: dict[tuple[int, int], deque[tuple[float, str, int]]] = defaultdict(deque)

    async def _enabled(self, interaction: discord.Interaction, module_id: str) -> bool:
        if interaction.guild is None or not self.storage.module_enabled(interaction.guild.id, module_id):
            await interaction.response.send_message("この機能は管理者により無効です。", ephemeral=True)
            return False
        return True

    async def _dm(self, member: discord.Member, text: str) -> bool:
        try:
            await member.send(text)
            return True
        except discord.HTTPException:
            return False

    async def _audit(self, guild: discord.Guild, text: str) -> None:
        module = self.storage.get_module(guild.id, "audit_log")
        channel_id = module["settings"].get("management_channel_id")
        if not module["enabled"] or not channel_id:
            return
        channel = guild.get_channel(int(channel_id))
        if isinstance(channel, discord.TextChannel):
            try:
                await channel.send(text, allowed_mentions=discord.AllowedMentions.none())
            except discord.HTTPException:
                LOGGER.warning("Could not write moderation audit log", exc_info=True)

    @staticmethod
    def _manageable(actor: discord.Member, target: discord.Member, action: str) -> str | None:
        return ModerationService.manageable(actor, target, action)

    async def _apply_case(self, guild: discord.Guild, member: discord.Member, action: str, reason: str | None, moderator_id: int | None, minutes: int = 0, notify: bool = True) -> None:
        await self.moderation.apply_case(guild, member, action, reason, moderator_id, minutes, notify)

    async def _warn(self, guild: discord.Guild, member: discord.Member, reason: str | None, moderator_id: int | None) -> int:
        return await self.moderation.warn(guild, member, reason, moderator_id)

    @app_commands.command(description="メンバーに警告を与えます。")
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def warn(self, interaction: discord.Interaction, member: discord.Member, reason: str | None = None):
        if not await self._enabled(interaction, "moderation"):
            return
        assert interaction.guild is not None
        error = self._manageable(interaction.user, member, "timeout")
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return
        count = await self._warn(interaction.guild, member, reason, interaction.user.id)
        await interaction.response.send_message(f"{member.mention} に警告しました（現在 {count} 回）。", ephemeral=True)

    @app_commands.command(description="メンバーを一時的にタイムアウトします。")
    @app_commands.checks.has_permissions(moderate_members=True)
    @app_commands.guild_only()
    async def timeout(self, interaction: discord.Interaction, member: discord.Member, minutes: int, reason: str | None = None):
        if not await self._enabled(interaction, "moderation"):
            return
        assert interaction.guild is not None
        error = self._manageable(interaction.user, member, "timeout")
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return
        try:
            await self._apply_case(interaction.guild, member, "timeout", reason, interaction.user.id, minutes, True)
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        await interaction.response.send_message("タイムアウトしました。", ephemeral=True)

    @app_commands.command(description="メンバーをキックします。")
    @app_commands.checks.has_permissions(kick_members=True)
    @app_commands.guild_only()
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str | None = None):
        if not await self._enabled(interaction, "moderation"):
            return
        assert interaction.guild is not None
        error = self._manageable(interaction.user, member, "kick")
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return
        await self._apply_case(interaction.guild, member, "kick", reason, interaction.user.id)
        await interaction.response.send_message("キックしました。", ephemeral=True)

    @app_commands.command(description="メンバーを追放します。")
    @app_commands.checks.has_permissions(ban_members=True)
    @app_commands.guild_only()
    async def ban(self, interaction: discord.Interaction, member: discord.Member, reason: str | None = None):
        if not await self._enabled(interaction, "moderation"):
            return
        assert interaction.guild is not None
        error = self._manageable(interaction.user, member, "ban")
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return
        await self._apply_case(interaction.guild, member, "ban", reason, interaction.user.id)
        await interaction.response.send_message("追放しました。", ephemeral=True)

    @staticmethod
    def _safe_regex(pattern: str) -> re.Pattern[str] | None:
        if not pattern or len(pattern) > 160 or re.search(r"\([^)]*[+*][^)]*\)[+*{]", pattern):
            return None
        try:
            return re.compile(pattern, re.IGNORECASE)
        except re.error:
            return None

    async def _filter_message(self, message: discord.Message, settings: dict) -> bool:
        content = message.content
        keywords = [x.strip().lower() for x in str(settings.get("filter_keywords", "")).splitlines() if x.strip()]
        if any(word in content.lower() for word in keywords):
            return True
        for raw in str(settings.get("filter_regex", "")).splitlines():
            regex = self._safe_regex(raw.strip())
            if regex:
                try:
                    if await asyncio.wait_for(asyncio.to_thread(regex.search, content[:2000]), timeout=0.05):
                        return True
                except TimeoutError:
                    LOGGER.warning("A filter regular expression exceeded its time budget")
        if not settings.get("safe_browsing_enabled") or not self.bot.settings.google_safe_browsing_api_key:
            return False
        for url in URL_RE.findall(content):
            digest = hashlib.sha256(url.encode()).hexdigest()
            unsafe = self.storage.cached_url_result(digest)
            if unsafe is None:
                payload = {"client": {"clientId": "tueka", "clientVersion": "1"}, "threatInfo": {"threatTypes": ["SOCIAL_ENGINEERING", "MALWARE"], "platformTypes": ["ANY_PLATFORM"], "threatEntryTypes": ["URL"], "threatEntries": [{"url": url}]}}
                try:
                    async with httpx.AsyncClient(timeout=3) as client:
                        response = await client.post("https://safebrowsing.googleapis.com/v4/threatMatches:find", params={"key": self.bot.settings.google_safe_browsing_api_key}, json=payload)
                        response.raise_for_status()
                    unsafe = bool(response.json().get("matches"))
                    self.storage.cache_url_result(digest, unsafe)
                except httpx.HTTPError:
                    LOGGER.warning("Safe Browsing lookup failed; message was not removed", exc_info=True)
                    continue
            if unsafe:
                return True
        return False

    async def _delete_and_warn(self, message: discord.Message, module: str, reason: str, issue_warning: bool = False) -> None:
        try:
            await message.delete()
        except discord.HTTPException:
            return
        self.storage.add_case(message.guild.id, message.author.id, module, reason)
        await self._audit(message.guild, f"`{module}`: {message.author} ({message.author.id}) / {reason}")
        if issue_warning and isinstance(message.author, discord.Member) and self.storage.module_enabled(message.guild.id, "moderation"):
            await self._warn(message.guild, message.author, reason, None)

    async def _legacy_on_message_disabled(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return
        guild_id = message.guild.id
        if self.storage.module_enabled(guild_id, "anti_spam"):
            settings = self.storage.get_module(guild_id, "anti_spam")["settings"]
            window = max(1, min(int(settings.get("spam_window_seconds", 10)), 300))
            key = (guild_id, message.author.id)
            queue = self.recent[key]
            now = time.monotonic()
            queue.append((now, message.content, len(message.mentions)))
            while queue and now - queue[0][0] > window:
                queue.popleft()
            message_limit = max(2, min(int(settings.get("spam_message_limit", 6)), 50))
            mention_limit = max(1, min(int(settings.get("spam_mention_limit", 10)), 100))
            duplicate_limit = max(2, min(int(settings.get("spam_duplicate_limit", 3)), 20))
            reason = None
            if len(queue) >= message_limit:
                reason = "メッセージの連投"
            elif sum(mentions for _, _, mentions in queue) >= mention_limit:
                reason = "メンションスパム"
            elif message.content and sum(text == message.content for _, text, _ in queue) >= duplicate_limit:
                reason = "重複メッセージ"
            if reason:
                await self._delete_and_warn(message, "anti_spam", reason, True)
                if settings.get("spam_action") == "timeout":
                    minutes = max(1, min(int(settings.get("spam_timeout_minutes", 10)), MAX_TIMEOUT))
                    member = message.author
                    if isinstance(member, discord.Member) and message.guild.me and not self._manageable(message.guild.me, member, "timeout"):
                        try:
                            await self._apply_case(message.guild, member, "timeout", reason, None, minutes, False)
                        except discord.HTTPException:
                            LOGGER.warning("Anti-spam timeout failed", exc_info=True)
                return
        if self.storage.module_enabled(guild_id, "chat_filter"):
            settings = self.storage.get_module(guild_id, "chat_filter")["settings"]
            if await self._filter_message(message, settings):
                await self._delete_and_warn(message, "chat_filter", "フィルタールールまたは危険なURLを検知", settings.get("filter_action") == "delete_warn")


async def setup(bot: commands.Bot):
    await bot.add_cog(SafetyCog(bot))
