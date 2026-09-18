"""Category-selectable server event logging."""
import time
from datetime import datetime, timezone
from typing import Any

import discord
from discord.ext import commands

from moderation import ModerationRepository
from guild_settings import GuildSettingsRepository


class AuditLogCog(commands.Cog):
    """Send selected server events to the configured server-log channel."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.moderation_repository = ModerationRepository(bot.settings.database_url)
        self.guild_settings = GuildSettingsRepository(bot.settings.database_url)
        self._recent_actions: dict[tuple[int, str, int], float] = {}

    @staticmethod
    def _short(value: Any, limit: int = 900) -> str:
        text = discord.utils.escape_markdown(str(value or "(なし)"))
        return text[: limit - 1] + "…" if len(text) > limit else text

    @staticmethod
    def _event_key(title: str) -> str | None:
        for token, event in (
            ("メッセージ編集", "message_edit"), ("メッセージ削除", "message_delete"),
            ("Timeout", "timeout"), ("Kick", "kick"), ("BAN解除", "unban"),
            ("BAN", "ban"), ("参加", "join"), ("退会", "leave"),
        ):
            if token in title:
                return event
        if any(token in title for token in ("更新", "作成", "ロール", "チャンネル", "サーバー", "ボイス")):
            return "admin"
        return None

    def _channel(self, guild: discord.Guild, category: str, event: str | None = None) -> discord.TextChannel | None:
        modern = self.guild_settings.get_module(guild.id, "moderation_logs")
        if modern["enabled"] and event and modern["settings"].get(f"log_{event}"):
            channel_id = modern["settings"].get("log_channel_id") or self.guild_settings.get_module(guild.id, "moderation")["settings"].get("default_log_channel_id")
            channel = guild.get_channel(int(channel_id)) if channel_id else None
            if isinstance(channel, discord.TextChannel):
                return channel
        module = self.guild_settings.get_module(guild.id, "audit_log")
        if not module["enabled"] or not module["settings"].get(f"log_{category}"):
            return None
        channel_id = module["settings"].get("management_channel_id")
        channel = guild.get_channel(int(channel_id)) if channel_id else None
        return channel if isinstance(channel, discord.TextChannel) else None

    async def _send(self, guild: discord.Guild, category: str, title: str, color: discord.Color, description: str | None = None, fields: list[tuple[str, Any]] | None = None) -> None:
        event = self._event_key(title)
        channel = self._channel(guild, category, event)
        if channel is None:
            return
        embed = discord.Embed(title=title, description=self._short(description) if description else None, color=color, timestamp=datetime.now(timezone.utc))
        for name, value in (fields or []):
            embed.add_field(name=name[:256], value=self._short(value), inline=False)
        try:
            await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except (discord.Forbidden, discord.HTTPException):
            return
        modern = self.guild_settings.get_module(guild.id, "moderation_logs")
        if event and modern["enabled"] and modern["settings"].get(f"log_{event}"):
            family = "anti_raid" if any(token in title for token in ("参加","退会")) else "infraction"
            self.moderation_repository.create_moderation_event(guild.id,family=family,event_type="infraction_change",source="discord_audit",
                reason=title,channel_id=channel.id,evidence={"description":description,"fields":fields or []},mode="enforce")

    def _claim_action(self, guild_id: int, action: str, user_id: int) -> bool:
        now = time.monotonic()
        self._recent_actions = {key: expiry for key, expiry in self._recent_actions.items() if expiry > now}
        key = (guild_id, action, user_id)
        if key in self._recent_actions:
            return False
        self._recent_actions[key] = now + 15
        return True

    async def _recent_audit(self, guild: discord.Guild, action: discord.AuditLogAction, target_id: int):
        try:
            async for entry in guild.audit_logs(limit=8, action=action):
                target = getattr(entry, "target", None)
                created_at = getattr(entry, "created_at", None)
                if target is not None and getattr(target, "id", None) == target_id and created_at and abs((datetime.now(timezone.utc) - created_at).total_seconds()) <= 20:
                    return entry
        except (discord.Forbidden, discord.HTTPException):
            return None
        return None

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot or message.guild is None:
            return
        await self._send(message.guild, "message", "📨 メッセージ投稿", discord.Color.green(), fields=[("投稿者", message.author.mention), ("チャンネル", message.channel.mention), ("本文", message.content or "(本文なし・添付あり)")])

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if before.author.bot or after.guild is None or before.content == after.content:
            return
        await self._send(after.guild, "message", "📝 メッセージ編集", discord.Color.orange(), fields=[("投稿者", after.author.mention), ("チャンネル", after.channel.mention), ("変更前", before.content or "(本文なし)"), ("変更後", after.content or "(本文なし)")])

    @commands.Cog.listener()
    async def on_raw_message_edit(self, payload: discord.RawMessageUpdateEvent) -> None:
        if payload.cached_message is not None or payload.guild_id is None:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if guild:
            await self._send(guild, "message", "📝 メッセージ編集", discord.Color.orange(), f"キャッシュ外のメッセージが編集されました。ID: `{payload.message_id}`")

    @commands.Cog.listener()
    async def on_raw_message_delete(self, payload: discord.RawMessageDeleteEvent) -> None:
        if payload.guild_id is None:
            return
        cached = payload.cached_message
        if cached is not None and cached.author.bot:
            return
        guild = self.bot.get_guild(payload.guild_id)
        if guild:
            body = cached.content if cached else f"キャッシュ外のメッセージです。ID: `{payload.message_id}`"
            author = cached.author.mention if cached else "不明"
            await self._send(guild, "message", "🗑️ メッセージ削除", discord.Color.red(), fields=[("投稿者", author), ("チャンネル", f"<#{payload.channel_id}>"), ("本文", body or "(本文なし)")])

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: discord.Member, before: discord.VoiceState, after: discord.VoiceState) -> None:
        if before.channel == after.channel:
            return
        if before.channel is None and after.channel is not None:
            title, detail = "🔊 VC参加", f"{member.mention} が {after.channel.mention} に参加しました。"
        elif before.channel is not None and after.channel is None:
            title, detail = "🔇 VC退出", f"{member.mention} が {before.channel.mention} から退出しました。"
        else:
            title, detail = "🔁 VC移動", f"{member.mention} が {before.channel.mention} から {after.channel.mention} へ移動しました。"
        await self._send(member.guild, "voice", title, discord.Color.blurple(), detail)

    async def _channel_event(self, channel: Any, action: str, before: Any | None = None) -> None:
        guild = channel.guild
        if before is None:
            description = f"{channel.mention if hasattr(channel, 'mention') else channel.name} を{action}しました。"
        elif action == "更新":
            changed = [label for attr, label in (("name", "名前"), ("category_id", "カテゴリー"), ("topic", "トピック"), ("slowmode_delay", "低速モード"), ("nsfw", "年齢制限")) if getattr(before, attr, None) != getattr(channel, attr, None)]
            if not changed:
                return
            description = f"{channel.mention if hasattr(channel, 'mention') else channel.name} を更新しました: {', '.join(changed)}"
        else:
            description = f"{channel.name} を{action}しました。"
        await self._send(guild, "channel", f"#️⃣ チャンネル{action}", discord.Color.teal(), description)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel) -> None:
        await self._channel_event(channel, "作成")

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel) -> None:
        await self._channel_event(channel, "削除")

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before, after) -> None:
        await self._channel_event(after, "更新", before)

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread) -> None:
        await self._channel_event(thread, "作成")

    @commands.Cog.listener()
    async def on_thread_delete(self, thread: discord.Thread) -> None:
        await self._channel_event(thread, "削除")

    @commands.Cog.listener()
    async def on_thread_update(self, before: discord.Thread, after: discord.Thread) -> None:
        await self._channel_event(after, "更新", before)

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        await self._send(member.guild, "member", "👋 メンバー参加", discord.Color.green(), f"{member.mention} が参加しました。")

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        if all(self._channel(member.guild, "member", event) is None for event in ("ban", "kick", "leave")):
            return
        ban = await self._recent_audit(member.guild, discord.AuditLogAction.ban, member.id)
        if ban and self._claim_action(member.guild.id, "ban", member.id):
            await self._send(member.guild, "member", "⛔ メンバーBAN", discord.Color.red(), fields=[("対象", str(member)), ("実行者", getattr(ban.user, "mention", "不明")), ("理由", ban.reason or "(なし)")])
            return
        kick = await self._recent_audit(member.guild, discord.AuditLogAction.kick, member.id)
        if kick and self._claim_action(member.guild.id, "kick", member.id):
            await self._send(member.guild, "member", "👢 メンバーKick", discord.Color.orange(), fields=[("対象", str(member)), ("実行者", getattr(kick.user, "mention", "不明")), ("理由", kick.reason or "(なし)")])
            return
        await self._send(member.guild, "member", "🚪 メンバー退会", discord.Color.light_grey(), f"{member} が退会しました。")

    @commands.Cog.listener()
    async def on_member_ban(self, guild: discord.Guild, user: discord.User) -> None:
        if self._channel(guild, "member", "ban") is None:
            return
        if not self._claim_action(guild.id, "ban", user.id):
            return
        entry = await self._recent_audit(guild, discord.AuditLogAction.ban, user.id)
        await self._send(guild, "member", "⛔ メンバーBAN", discord.Color.red(), fields=[("対象", str(user)), ("実行者", getattr(getattr(entry, "user", None), "mention", "不明")), ("理由", getattr(entry, "reason", None) or "(なし)")])

    @commands.Cog.listener()
    async def on_member_unban(self, guild: discord.Guild, user: discord.User) -> None:
        if self._channel(guild, "member", "unban") is None:
            return
        entry = await self._recent_audit(guild, discord.AuditLogAction.unban, user.id)
        await self._send(guild, "member", "✅ BAN解除", discord.Color.green(), fields=[("対象", str(user)), ("実行者", getattr(getattr(entry, "user", None), "mention", "不明")), ("理由", getattr(entry, "reason", None) or "(なし)")])

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member) -> None:
        changes = []
        if before.nick != after.nick:
            changes.append(("ニックネーム", f"{before.nick or before.name} → {after.nick or after.name}"))
        before_roles, after_roles = {role.id: role.name for role in before.roles[1:]}, {role.id: role.name for role in after.roles[1:]}
        added, removed = set(after_roles) - set(before_roles), set(before_roles) - set(after_roles)
        if added:
            changes.append(("追加ロール", ", ".join(after_roles[role_id] for role_id in sorted(added))))
        if removed:
            changes.append(("削除ロール", ", ".join(before_roles[role_id] for role_id in sorted(removed))))
        if changes:
            await self._send(after.guild, "member", "👤 メンバー情報更新", discord.Color.blurple(), fields=[("対象", after.mention), *changes])

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: discord.Role) -> None:
        await self._send(role.guild, "role", "➕ ロール作成", discord.Color.green(), f"{role.name} を作成しました。")

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: discord.Role) -> None:
        await self._send(role.guild, "role", "➖ ロール削除", discord.Color.red(), f"{role.name} を削除しました。")

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: discord.Role, after: discord.Role) -> None:
        changed = [label for attr, label in (("name", "名前"), ("colour", "色"), ("permissions", "権限"), ("hoist", "表示位置"), ("mentionable", "メンション可否")) if getattr(before, attr) != getattr(after, attr)]
        if changed:
            await self._send(after.guild, "role", "✏️ ロール更新", discord.Color.orange(), f"{after.name} を更新しました: {', '.join(changed)}")

    @commands.Cog.listener()
    async def on_guild_update(self, before: discord.Guild, after: discord.Guild) -> None:
        changed = [label for attr, label in (("name", "名前"), ("icon", "アイコン"), ("verification_level", "認証レベル"), ("explicit_content_filter", "コンテンツフィルター"), ("default_notifications", "通知設定"), ("afk_channel", "AFKチャンネル")) if getattr(before, attr, None) != getattr(after, attr, None)]
        if changed:
            await self._send(after, "server", "⚙️ サーバー設定更新", discord.Color.gold(), f"更新項目: {', '.join(changed)}")


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(AuditLogCog(bot))
