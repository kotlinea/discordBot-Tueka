"""Shared moderation action executor for manual commands and AutoMod."""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

import discord

from storage import GuildStorage


LOGGER = logging.getLogger(__name__)
MAX_TIMEOUT_MINUTES = 28 * 24 * 60


@dataclass(slots=True)
class ActionContext:
    guild: discord.Guild
    member: discord.Member | None = None
    message: discord.Message | None = None
    channel: discord.abc.GuildChannel | discord.Thread | None = None
    reaction: discord.Reaction | None = None
    actor: discord.abc.User | None = None


class ModerationService:
    def __init__(self, bot: discord.Client, storage: GuildStorage) -> None:
        self.bot, self.storage = bot, storage

    @staticmethod
    def manageable(actor: discord.Member | None, target: discord.Member, action: str) -> str | None:
        if actor is not None and target.id == actor.id:
            return "自分自身にはこの処置を実行できません。"
        if target.id == target.guild.owner_id:
            return "サーバー所有者にはこの処置を実行できません。"
        bot_member = target.guild.me
        if bot_member is None or target.top_role >= bot_member.top_role:
            return "Botより同等以上のロールを持つメンバーには実行できません。"
        if actor is not None and target.top_role >= actor.top_role and actor.id != target.guild.owner_id:
            return "自分より同等以上のロールを持つメンバーには実行できません。"
        permission = {"timeout": "moderate_members", "untimeout": "moderate_members", "kick": "kick_members", "ban": "ban_members", "tempban": "ban_members", "softban": "ban_members"}.get(action)
        if permission and not getattr(bot_member.guild_permissions, permission):
            return "Botに必要なDiscord権限がありません。"
        return None

    @staticmethod
    async def dm(member: discord.Member, text: str) -> bool:
        try:
            await member.send(text[:2000])
            return True
        except (discord.Forbidden, discord.HTTPException):
            return False

    def _log_channel(self, guild: discord.Guild, automod_settings: dict[str, Any] | None = None) -> discord.TextChannel | None:
        channel_id = (automod_settings or {}).get("log_channel_id")
        if not channel_id:
            logs = self.storage.get_module(guild.id, "moderation_logs")
            if logs["enabled"]:
                channel_id = logs["settings"].get("log_channel_id")
        if not channel_id:
            core = self.storage.get_module(guild.id, "moderation")
            channel_id = core["settings"].get("default_log_channel_id")
        if not channel_id:
            audit = self.storage.get_module(guild.id, "audit_log")
            if audit["enabled"]:
                channel_id = audit["settings"].get("management_channel_id")
        channel = guild.get_channel(int(channel_id)) if channel_id else None
        return channel if isinstance(channel, discord.TextChannel) else None

    async def log_manual(self, guild: discord.Guild, title: str, description: str, *, category: str = "admin") -> None:
        logs = self.storage.get_module(guild.id, "moderation_logs")
        if logs["enabled"] and not logs["settings"].get(f"log_{category}", False):
            return
        channel = self._log_channel(guild)
        if channel is None:
            return
        embed = discord.Embed(title=title[:256], description=description[:4000], color=discord.Color.orange())
        try:
            await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            LOGGER.warning("Could not write moderation log", exc_info=True)

    async def apply_case(self, guild: discord.Guild, member: discord.Member, action: str, reason: str | None,
                         moderator_id: int | None = None, duration_minutes: int = 0, notify: bool = True,
                         *, automod_event_id: int | None = None, rule_id: int | None = None,
                         moderation_event_id: int | None = None, moderation_rule_id: int | None = None,
                         source: str = "manual", actor: discord.Member | None = None) -> int:
        error = self.manageable(actor, member, action)
        if error:
            raise PermissionError(error)
        expires_at: int | None = None
        if action == "timeout":
            if not 1 <= duration_minutes <= MAX_TIMEOUT_MINUTES:
                raise ValueError("タイムアウトは1分から28日以内です。")
            await member.timeout(timedelta(minutes=duration_minutes), reason=reason)
            expires_at = int(time.time()) + duration_minutes * 60
        elif action == "kick":
            await member.kick(reason=reason)
        elif action in {"ban", "tempban", "softban"}:
            if action == "tempban":
                if not 1 <= duration_minutes <= 525600:
                    raise ValueError("一時Banは1分から365日以内です。")
                expires_at = int(time.time()) + duration_minutes * 60
            await guild.ban(member, reason=reason)
            if action == "softban":
                await guild.unban(discord.Object(id=member.id), reason=f"Softban: {reason or 'なし'}")
        elif action == "untimeout":
            await member.timeout(None, reason=reason)
        else:
            raise ValueError("Unknown moderation action")
        dm_sent = await self.dm(member, f"{guild.name}で {action} が実行されました。理由: {reason or 'なし'}") if notify else False
        case_id = self.storage.add_case(guild.id, member.id, action, reason, moderator_id, expires_at, dm_sent,
            automod_event_id=automod_event_id, rule_id=rule_id, moderation_event_id=moderation_event_id,
            moderation_rule_id=moderation_rule_id, source=source)
        if action == "tempban" and expires_at:
            self.storage.schedule_moderation_action(guild.id, member.id, "unban", expires_at, reason, case_id)
        if source == "manual":
            await self.log_manual(guild, f"Moderation Case #{case_id}", f"`{action}`: {member} ({member.id})\n理由: {reason or 'なし'}",
                category="timeout" if action in {"timeout", "untimeout"} else action if action in {"kick", "ban", "unban"} else "admin")
        return case_id

    async def warn(self, guild: discord.Guild, member: discord.Member, reason: str | None, moderator_id: int | None,
                   *, notify: bool | None = None, actor: discord.Member | None = None) -> int:
        if actor is not None:
            error = self.manageable(actor, member, "timeout")
            if error:
                raise PermissionError(error)
        module = self.storage.get_module(guild.id, "moderation")["settings"]
        should_notify = bool(module.get("dm_notify")) if notify is None else notify
        dm_sent = await self.dm(member, f"{guild.name}で警告を受けました。理由: {reason or 'なし'}") if should_notify else False
        _, before, after = self.storage.add_points(guild.id, member.id, 1, reason, expires_at=None)
        case_id = self.storage.add_case(guild.id, member.id, "warn", reason, moderator_id, None, dm_sent, source="manual", points=1)
        await self.log_manual(guild, f"Moderation Case #{case_id}", f"`warn` ({after}pt): {member} ({member.id})\n理由: {reason or 'なし'}", category="warning")
        await self._apply_threshold(guild, member, before, after, reason or "警告ポイント", None, None)
        return self.storage.get_user(guild.id, member.id)["warn"]

    async def _apply_threshold(self, guild: discord.Guild, member: discord.Member, before: int, after: int, reason: str,
                               event_id: int | None, rule_id: int | None) -> dict[str, Any] | None:
        infraction_module = self.storage.get_module(guild.id, "infractions")
        thresholds = infraction_module["settings"].get("point_thresholds", []) if infraction_module["enabled"] else []
        if not thresholds and not self.storage.moderation_v2_migrated(guild.id):
            thresholds = self.storage.get_module(guild.id, "automod")["settings"].get("point_thresholds", [])
        if not thresholds and self.storage.moderation_v2_migrated(guild.id):
            return None
        if not thresholds:
            legacy = self.storage.get_module(guild.id, "moderation")["settings"]
            if legacy.get("escalation_enabled"):
                action = {"type": legacy.get("escalation_action", "timeout")}
                if action["type"] == "timeout":
                    action["duration_minutes"] = int(legacy.get("escalation_timeout_minutes", 60))
                thresholds = [{"points": int(legacy.get("escalation_threshold", 3)), "action": action}]
        crossed = [item for item in thresholds if before < int(item.get("points", 0)) <= after]
        if not crossed:
            return None
        selected = max(crossed, key=lambda item: int(item["points"]))
        action = dict(selected.get("action") or {})
        action_type = action.get("type")
        if action_type not in {"timeout", "kick", "ban", "tempban"}:
            return None
        try:
            case_id = await self.apply_case(guild, member, action_type, f"{reason}: {after}ポイントに到達", None,
                int(action.get("duration_minutes", 0)), False, moderation_event_id=event_id,
                moderation_rule_id=rule_id, source="infraction")
            return {"type": "threshold", "status": "success", "action": action_type, "case_id": case_id, "points": selected["points"]}
        except (ValueError, PermissionError, discord.HTTPException) as exc:
            return {"type": "threshold", "status": "failed", "action": action_type, "error": str(exc)[:300]}

    @staticmethod
    def _message_template(text: str, member: discord.Member, reason: str) -> str:
        return text.replace("{user}", member.mention).replace("{username}", member.name).replace("{reason}", reason)[:2000]

    @staticmethod
    def _overwrite_value(value: bool | None) -> bool | None:
        return value if value in {True, False} else None

    async def lockdown(self, guild: discord.Guild, reason: str, duration_minutes: int, *, started_by: int | None = None,
            source_event_id: int | None = None, channel_ids: list[int] | None = None, category_ids: list[int] | None = None) -> int:
        me = guild.me
        if me is None or not me.guild_permissions.manage_channels:
            raise PermissionError("Botにチャンネル管理権限がありません。")
        unlock_at = int(time.time()) + max(1, min(duration_minutes, 1440)) * 60
        lockdown_id = self.storage.start_lockdown(guild.id, reason=reason, started_by=started_by, unlock_at=unlock_at, source_event_id=source_event_id)
        selected = set(channel_ids or [])
        categories = set(category_ids or [])
        channels = [channel for channel in guild.channels if isinstance(channel, (discord.TextChannel, discord.ForumChannel))
            and (not selected and not categories or channel.id in selected or getattr(channel, "category_id", None) in categories)]
        role = guild.default_role
        for channel in channels:
            overwrite = channel.overwrites_for(role)
            before = {"send_messages": self._overwrite_value(overwrite.send_messages), "send_messages_in_threads": self._overwrite_value(overwrite.send_messages_in_threads)}
            overwrite.send_messages = False
            overwrite.send_messages_in_threads = False
            await channel.set_permissions(role, overwrite=overwrite, reason=f"Moderation lockdown #{lockdown_id}: {reason}")
            self.storage.save_lockdown_snapshot(lockdown_id, channel.id, role.id, before, {"send_messages": False, "send_messages_in_threads": False})
        self.storage.set_raid_state(guild.id, True, lockdown_id=lockdown_id)
        return lockdown_id

    async def unlock_lockdown(self, guild: discord.Guild, lockdown_id: int | None = None) -> dict[str, int]:
        active = self.storage.active_lockdown(guild.id)
        if not active or lockdown_id and int(active["id"]) != lockdown_id:
            return {"restored": 0, "conflicts": 0}
        restored = conflicts = 0
        for snapshot in self.storage.lockdown_snapshots(int(active["id"])):
            channel = guild.get_channel(int(snapshot["channel_id"]))
            role = guild.get_role(int(snapshot["role_id"]))
            if channel is None or role is None or not hasattr(channel, "overwrites_for"):
                conflicts += 1
                continue
            overwrite = channel.overwrites_for(role)
            current = {"send_messages": self._overwrite_value(overwrite.send_messages), "send_messages_in_threads": self._overwrite_value(overwrite.send_messages_in_threads)}
            if current != snapshot["applied"]:
                conflicts += 1
                continue
            overwrite.send_messages = snapshot["before"].get("send_messages")
            overwrite.send_messages_in_threads = snapshot["before"].get("send_messages_in_threads")
            await channel.set_permissions(role, overwrite=overwrite, reason=f"Moderation lockdown #{active['id']} ended")
            restored += 1
        self.storage.finish_lockdown(int(active["id"]), error=f"{conflicts} overwrite conflicts" if conflicts else None)
        self.storage.set_raid_state(guild.id, False)
        return {"restored": restored, "conflicts": conflicts}

    async def execute_actions(self, context: ActionContext, rule: dict[str, Any], reason: str, event_id: int,
            settings: dict[str, Any]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        member, message, guild = context.member, context.message, context.guild
        for action in rule.get("actions", []):
            action_type = action["type"]
            if rule.get("mode") == "monitor":
                results.append({"type": action_type, "status": "simulated"})
                continue
            try:
                if action_type == "delete":
                    if message is None:
                        raise ValueError("削除対象メッセージがありません")
                    try:
                        await message.delete()
                    except discord.NotFound:
                        pass
                    results.append({"type": action_type, "status": "success"})
                elif action_type == "purge":
                    channel = context.channel or (message.channel if message else None)
                    if not isinstance(channel, discord.TextChannel):
                        raise ValueError("削除対象チャンネルがありません")
                    deleted = await channel.purge(limit=int(action.get("count", 10)), check=(lambda item: member is None or item.author.id == member.id))
                    results.append({"type": action_type, "status": "success", "count": len(deleted)})
                elif action_type == "remove_reaction":
                    if context.reaction is None or context.actor is None:
                        raise ValueError("リアクション情報がありません")
                    await context.reaction.remove(context.actor)
                    results.append({"type": action_type, "status": "success"})
                elif action_type == "points":
                    if member is None:
                        raise ValueError("対象メンバーが見つかりません")
                    expiry_days = int(action.get("expires_days", 30))
                    expires_at = int(time.time()) + expiry_days * 86400 if expiry_days else None
                    _, before, after = self.storage.add_points(guild.id, member.id, int(action.get("points", 1)), reason,
                        rule_id=rule.get("legacy_rule_id"), moderation_rule_id=rule.get("id"), moderation_event_id=event_id, expires_at=expires_at)
                    case_id = self.storage.add_case(guild.id, member.id, "warn", reason, None, expires_at, False,
                        moderation_event_id=event_id, moderation_rule_id=rule.get("id"), source=rule.get("family", "automod"), points=int(action.get("points", 1)))
                    results.append({"type": action_type, "status": "success", "case_id": case_id, "before": before, "after": after})
                    threshold = await self._apply_threshold(guild, member, before, after, reason, event_id, rule.get("id"))
                    if threshold:
                        results.append(threshold)
                elif action_type == "notify":
                    target = guild.get_channel(int(action["channel_id"])) if action.get("channel_id") else context.channel
                    if not isinstance(target, (discord.TextChannel, discord.Thread)):
                        raise ValueError("通知チャンネルが見つかりません")
                    text = action.get("message", "ルール違反を検知しました。")
                    if member:
                        text = self._message_template(text, member, reason)
                    await target.send(text[:2000], allowed_mentions=discord.AllowedMentions.none())
                    results.append({"type": action_type, "status": "success"})
                elif action_type == "dm":
                    if member is None:
                        raise ValueError("対象メンバーが見つかりません")
                    sent = await self.dm(member, self._message_template(action.get("message", "ルール違反を検知しました: {reason}"), member, reason))
                    results.append({"type": action_type, "status": "success" if sent else "failed"})
                elif action_type in {"timeout", "untimeout", "kick", "ban", "tempban", "softban"}:
                    if member is None:
                        raise ValueError("対象メンバーが見つかりません")
                    case_id = await self.apply_case(guild, member, action_type, reason, None, int(action.get("duration_minutes", 0)), False,
                        moderation_event_id=event_id, moderation_rule_id=rule.get("id"), source=rule.get("family", "automod"))
                    results.append({"type": action_type, "status": "success", "case_id": case_id})
                elif action_type in {"lock", "unlock"}:
                    channel = context.channel or (message.channel if message else None)
                    if not isinstance(channel, (discord.TextChannel, discord.ForumChannel)):
                        raise ValueError("対象チャンネルがありません")
                    overwrite = channel.overwrites_for(guild.default_role)
                    overwrite.send_messages = False if action_type == "lock" else None
                    await channel.set_permissions(guild.default_role, overwrite=overwrite, reason=reason)
                    results.append({"type": action_type, "status": "success"})
                elif action_type == "lockdown":
                    lockdown_id = await self.lockdown(guild, reason, int(action.get("duration_minutes", 30)), source_event_id=event_id,
                        channel_ids=action.get("channel_ids"), category_ids=action.get("category_ids"))
                    results.append({"type": action_type, "status": "success", "lockdown_id": lockdown_id})
                elif action_type == "unlockdown":
                    result = await self.unlock_lockdown(guild)
                    results.append({"type": action_type, "status": "success", **result})
                elif action_type == "log":
                    results.append({"type": action_type, "status": "success"})
                elif action_type == "unban":
                    if member is None:
                        raise ValueError("対象ユーザーが見つかりません")
                    await guild.unban(discord.Object(id=member.id), reason=reason)
                    results.append({"type": action_type, "status": "success"})
            except (ValueError, PermissionError, discord.Forbidden, discord.HTTPException) as exc:
                results.append({"type": action_type, "status": "failed", "error": str(exc)[:300]})
        return results

    async def log_event(self, context: ActionContext, rule: dict[str, Any], event_id: int, reason: str,
            results: list[dict[str, Any]], settings: dict[str, Any]) -> None:
        logs = self.storage.get_module(context.guild.id, "moderation_logs")
        family = str(rule.get("family", "automod"))
        category = family if family in {"automod", "anti_spam", "anti_raid"} else "admin"
        if not logs["enabled"] or not logs["settings"].get(f"log_{category}", False):
            return
        channel = self._log_channel(context.guild, settings)
        if channel is None:
            return
        rendered = ", ".join(f"{item.get('type')}: {item.get('status')}" for item in results) or "記録のみ"
        embed = discord.Embed(title=f"Moderation Event #{event_id}", description=reason[:4000],
            color=discord.Color.gold() if rule.get("mode") == "monitor" else discord.Color.red())
        embed.add_field(name="機能 / ルール", value=f"{rule.get('family')} / {rule.get('name')} (`{rule.get('trigger_type')}`)", inline=False)
        if context.member:
            embed.add_field(name="対象", value=f"{context.member} ({context.member.id})", inline=False)
        if context.channel:
            embed.add_field(name="チャンネル", value=f"#{getattr(context.channel, 'name', context.channel.id)} ({context.channel.id})", inline=False)
        embed.add_field(name="実行結果", value=rendered[:1024], inline=False)
        try:
            await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            LOGGER.warning("Could not write Moderation log", exc_info=True)

    async def execute_rule(self, message: discord.Message, rule: dict[str, Any], reason: str, event_id: int,
                           automod_settings: dict[str, Any]) -> list[dict[str, Any]]:
        member = message.author if isinstance(message.author, discord.Member) else None
        results = await self.execute_actions(ActionContext(message.guild, member, message, message.channel, actor=message.author), rule, reason, event_id, automod_settings)
        await self.log_automod(message, rule, event_id, reason, results, automod_settings)
        return results

    async def log_automod(self, message: discord.Message, rule: dict[str, Any], event_id: int, reason: str,
                          results: list[dict[str, Any]], settings: dict[str, Any]) -> None:
        channel = self._log_channel(message.guild, settings)
        if channel is None:
            return
        rendered = ", ".join(f"{item.get('type')}: {item.get('status')}" for item in results) or "記録のみ"
        embed = discord.Embed(title=f"AutoMod Event #{event_id}", description=reason[:4000],
            color=discord.Color.gold() if rule.get("mode") == "monitor" else discord.Color.red())
        embed.add_field(name="ルール", value=f"{rule.get('name')} (`{rule.get('trigger_type')}`)", inline=False)
        embed.add_field(name="対象", value=f"{message.author} ({message.author.id})", inline=False)
        embed.add_field(name="チャンネル", value=f"#{getattr(message.channel, 'name', message.channel.id)} ({message.channel.id})", inline=False)
        embed.add_field(name="実行結果", value=rendered[:1024], inline=False)
        try:
            await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException:
            LOGGER.warning("Could not write AutoMod log", exc_info=True)
