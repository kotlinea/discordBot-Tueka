"""Guild-scoped safety modules: moderation, filtering, spam and reaction roles."""
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


MAX_TIMEOUT = 28 * 24 * 60
URL_RE = re.compile(r"https?://[^\s<>]+", re.I)
LOGGER = logging.getLogger(__name__)


class SafetyCog(commands.Cog):
    def __init__(self, bot: commands.Bot) -> None:
        self.bot, self.storage = bot, GuildStorage(bot.settings.database_path)
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
        if target.id == actor.id:
            return "自分自身にはこの処置を実行できません。"
        if target.id == target.guild.owner_id:
            return "サーバー所有者にはこの処置を実行できません。"
        me = target.guild.me
        if me is None or target.top_role >= me.top_role:
            return "Botより同等以上のロールを持つメンバーには実行できません。"
        if target.top_role >= actor.top_role and actor.id != target.guild.owner_id:
            return "自分より同等以上のロールを持つメンバーには実行できません。"
        permission = {"timeout": "moderate_members", "kick": "kick_members", "ban": "ban_members"}[action]
        if not getattr(me.guild_permissions, permission):
            return "Botに必要なDiscord権限がありません。"
        return None

    async def _apply_case(self, guild: discord.Guild, member: discord.Member, action: str, reason: str | None, moderator_id: int | None, minutes: int = 0, notify: bool = True) -> None:
        if action == "timeout":
            if not 1 <= minutes <= MAX_TIMEOUT:
                raise ValueError("タイムアウトは1分から28日以内です。")
            await member.timeout(timedelta(minutes=minutes), reason=reason)
        elif action == "kick":
            await member.kick(reason=reason)
        elif action == "ban":
            await member.ban(reason=reason)
        dm_sent = await self._dm(member, f"{guild.name}で {action} が実行されました。理由: {reason or 'なし'}") if notify else False
        expires_at = int(time.time()) + minutes * 60 if action == "timeout" else None
        self.storage.add_case(guild.id, member.id, action, reason, moderator_id, expires_at, dm_sent)
        await self._audit(guild, f"`{action}`: {member} ({member.id}) / 理由: {reason or 'なし'} / DM: {'送信済み' if dm_sent else '未送信'}")

    async def _warn(self, guild: discord.Guild, member: discord.Member, reason: str | None, moderator_id: int | None) -> int:
        count = self.storage.add_warning(guild.id, member.id)
        module = self.storage.get_module(guild.id, "moderation")["settings"]
        notify = bool(module.get("dm_notify"))
        dm_sent = await self._dm(member, f"{guild.name}で警告を受けました。理由: {reason or 'なし'}") if notify else False
        self.storage.add_case(guild.id, member.id, "warn", reason, moderator_id, None, dm_sent)
        await self._audit(guild, f"`warn` ({count}): {member} ({member.id}) / 理由: {reason or 'なし'}")
        if not module.get("escalation_enabled") or count < int(module.get("escalation_threshold", 3)):
            return count
        action = module.get("escalation_action", "timeout")
        minutes = int(module.get("escalation_timeout_minutes", 60))
        error = self._manageable(guild.me, member, action) if guild.me else "Bot情報を取得できません。"
        if error:
            await self._audit(guild, f"自動エスカレーションを実行できません: {error}")
            return count
        try:
            await self._apply_case(guild, member, action, f"警告数が {count} 回に到達", None, minutes, notify)
        except discord.HTTPException:
            LOGGER.warning("Automatic moderation escalation failed", exc_info=True)
        return count

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

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
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

    @app_commands.command(description="ダッシュボードのリアクションロール設定からボタンパネルを投稿します。")
    @app_commands.checks.has_permissions(manage_roles=True)
    @app_commands.guild_only()
    async def publish_reaction_roles(self, interaction: discord.Interaction):
        if not await self._enabled(interaction, "reaction_roles"):
            return
        assert interaction.guild is not None
        settings = self.storage.get_module(interaction.guild.id, "reaction_roles")["settings"]
        channel = interaction.guild.get_channel(int(settings.get("reaction_role_channel_id", 0)))
        role_ids = [int(role_id) for role_id in settings.get("reaction_role_ids", [])][:25]
        if not isinstance(channel, discord.TextChannel) or not role_ids:
            await interaction.response.send_message("ダッシュボードで投稿先チャンネルとロールを設定してください。", ephemeral=True)
            return
        roles = [interaction.guild.get_role(role_id) for role_id in role_ids]
        roles = [role for role in roles if role and not role.is_default() and not role.managed and interaction.guild.me and role < interaction.guild.me.top_role]
        if not roles:
            await interaction.response.send_message("Botが付与できるロールがありません。", ephemeral=True)
            return
        view = discord.ui.View(timeout=None)
        for role in roles:
            view.add_item(discord.ui.Button(label=role.name[:80], style=discord.ButtonStyle.secondary, custom_id=f"tueka-rr:{role.id}"))
        panel = await channel.send(embed=discord.Embed(title=str(settings.get("reaction_role_title") or "ロールを選択"), description=str(settings.get("reaction_role_description") or "ボタンでロールを付与・解除できます。")), view=view)
        self.storage.save_reaction_role_panel(panel.id, interaction.guild.id, [role.id for role in roles])
        await interaction.response.send_message("リアクションロールパネルを投稿しました。", ephemeral=True)

    @commands.Cog.listener()
    async def on_interaction(self, interaction: discord.Interaction):
        if interaction.type is not discord.InteractionType.component or not interaction.guild or not isinstance(interaction.user, discord.Member):
            return
        custom_id = (interaction.data or {}).get("custom_id", "")
        if not isinstance(custom_id, str) or not custom_id.startswith("tueka-rr:") or interaction.message is None:
            return
        panel = self.storage.reaction_role_panel(interaction.message.id)
        if not panel or panel["guild_id"] != interaction.guild.id or not self.storage.module_enabled(interaction.guild.id, "reaction_roles"):
            await interaction.response.send_message("このロールパネルは現在利用できません。", ephemeral=True)
            return
        try:
            role_id = int(custom_id.split(":", 1)[1])
        except ValueError:
            return
        role = interaction.guild.get_role(role_id)
        me = interaction.guild.me
        if role_id not in panel["role_ids"] or role is None or role.managed or role.is_default() or me is None or role >= me.top_role:
            await interaction.response.send_message("このロールは付与できません。", ephemeral=True)
            return
        try:
            if role in interaction.user.roles:
                await interaction.user.remove_roles(role, reason="Reaction role button")
                message = f"{role.name} を解除しました。"
            else:
                await interaction.user.add_roles(role, reason="Reaction role button")
                message = f"{role.name} を付与しました。"
            await interaction.response.send_message(message, ephemeral=True)
        except discord.HTTPException:
            await interaction.response.send_message("ロールを変更できませんでした。Botの権限とロール順を確認してください。", ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(SafetyCog(bot))
