"""Shared moderation action executor for manual commands and AutoMod."""
from __future__ import annotations

import logging
import time
import uuid
import json
from typing import Any
from jobs import LostLease
from jobs.leases import ResourceLease

from .contracts import ActionContext, ActionFailure, GuildRef, MemberRef, ChannelRef, ModerationPort

from moderation import ModerationRepository
from guild_settings import GuildSettingsRepository


LOGGER = logging.getLogger(__name__)
MAX_TIMEOUT_MINUTES = 28 * 24 * 60


class ModerationService:
    def __init__(self, port: ModerationPort, repository: ModerationRepository, guild_settings: GuildSettingsRepository) -> None:
        self.port, self.repository = port, repository
        self.guild_settings = guild_settings

    def manageable(self, actor: MemberRef | None, target: MemberRef, action: str) -> str | None:
        return self.port.manageable(actor, target, action)

    async def dm(self, member: MemberRef, text: str) -> bool:
        return await self.port.dm(member, text)

    def _log_channel(self, guild: GuildRef, automod_settings: dict[str, Any] | None = None) -> int | None:
        channel_id = (automod_settings or {}).get("log_channel_id")
        if not channel_id:
            logs = self.guild_settings.get_module(guild.id, "moderation_logs")
            if logs["enabled"]:
                channel_id = logs["settings"].get("log_channel_id")
        if not channel_id:
            core = self.guild_settings.get_module(guild.id, "moderation")
            channel_id = core["settings"].get("default_log_channel_id")
        if not channel_id:
            audit = self.guild_settings.get_module(guild.id, "audit_log")
            if audit["enabled"]:
                channel_id = audit["settings"].get("management_channel_id")
        return int(channel_id) if channel_id else None

    async def log_manual(self, guild: GuildRef, title: str, description: str, *, category: str = "admin") -> None:
        logs = self.guild_settings.get_module(guild.id, "moderation_logs")
        if logs["enabled"] and not logs["settings"].get(f"log_{category}", False):
            return
        channel_id = self._log_channel(guild)
        if channel_id is None:
            return
        try:
            await self.port.send(channel_id, embed={"title": title[:256], "description": description[:4000], "color": 0xe67e22})
        except ActionFailure:
            LOGGER.warning("Could not write moderation log", exc_info=True)

    async def apply_case(self, guild: GuildRef, member: MemberRef, action: str, reason: str | None,
                         moderator_id: int | None = None, duration_minutes: int = 0, notify: bool = True,
                         *, moderation_event_id: int | None = None, moderation_rule_id: int | None = None,
                         source: str = "manual", actor: MemberRef | None = None, execution_key: str | None = None) -> int:
        lease = ResourceLease(self.repository.database_url, 'moderation_member', f'{guild.id}:{member.id}')
        try:
            return await lease.run(lambda owned: self._apply_case_owned(guild, member, action, reason,
                moderator_id, duration_minutes, notify, moderation_event_id=moderation_event_id,
                moderation_rule_id=moderation_rule_id, source=source, actor=actor,
                execution_key=execution_key, lease=owned))
        except LostLease as exc:
            raise ActionFailure(str(exc), retry=True, partial=True) from exc

    async def _apply_case_owned(self, guild, member, action, reason, moderator_id, duration_minutes, notify,
            *, moderation_event_id, moderation_rule_id, source, actor, execution_key, lease):
        key = 'case:' + (execution_key or (f'{moderation_event_id}:{moderation_rule_id}:{member.id}:{action}' if moderation_event_id is not None else uuid.uuid4().hex))
        previous = self.repository.case_execution(guild.id, key)
        if previous is not None:
            if previous['case_id'] is not None:
                return int(previous['case_id'])
            raise ActionFailure('前回の実行結果を照合する必要があります。', partial=True)
        error = self.manageable(actor, member, action)
        if error:
            raise PermissionError(error)
        expires_at: int | None = None
        if action == "timeout":
            if not 1 <= duration_minutes <= MAX_TIMEOUT_MINUTES:
                raise ValueError("タイムアウトは1分から28日以内です。")
            expires_at = int(time.time()) + duration_minutes * 60
        elif action == "tempban":
            if not 1 <= duration_minutes <= 525600:
                raise ValueError("一時Banは1分から365日以内です。")
            expires_at = int(time.time()) + duration_minutes * 60
        elif action not in {"kick", "ban", "softban", "untimeout", "unban"}:
            raise ValueError("Unknown moderation action")
        execution = self.repository.create_moderation_event(guild.id, family='infraction', event_type='infraction_change',
            source='case_execution', reason=reason or '', actor_id=moderator_id, target_user_id=member.id,
            dedupe_key=key, evidence={'action': action, 'expires_at': expires_at, 'parent_event_id': moderation_event_id,
                                    'rule_id': moderation_rule_id, 'source': source}, lease=lease)
        if execution is None:
            raise ActionFailure('同じ処置が既に実行中です。', partial=True)
        try:
            await self.port.member_action(guild.id, member.id, action, reason, duration_minutes, execution)
        except ActionFailure as exc:
            self.repository.finish_moderation_event(execution, [{'type': action, 'status': 'partial' if exc.partial else 'failed',
                'error': str(exc)[:300], 'retry': exc.retry}])
            raise
        dm_sent = await self.dm(member, f"{guild.name}で {action} が実行されました。理由: {reason or 'なし'}") if notify else False
        case_id = self.repository.add_case(guild.id, member.id, action, reason, moderator_id, expires_at, dm_sent,
            moderation_event_id=moderation_event_id,
            moderation_rule_id=moderation_rule_id, source=source, execution_event_id=execution, lease=lease)
        if source == "manual":
            await self.log_manual(guild, f"Moderation Case #{case_id}", f"`{action}`: {member} ({member.id})\n理由: {reason or 'なし'}",
                category="timeout" if action in {"timeout", "untimeout"} else action if action in {"kick", "ban", "unban"} else "admin")
        return case_id

    async def reconcile_case(self, guild: GuildRef, execution_key: str) -> int:
        receipt = self.repository.case_execution(guild.id, 'case:' + execution_key)
        if receipt is None:
            raise ValueError('実行記録が見つかりません。')
        lease = ResourceLease(self.repository.database_url, 'moderation_member', f"{guild.id}:{receipt['target_user_id']}")
        try:
            return await lease.run(lambda owned: self._reconcile_case_owned(guild, receipt, owned))
        except LostLease as exc:
            raise ActionFailure(str(exc), retry=True, partial=True) from exc

    async def _reconcile_case_owned(self, guild, receipt, lease):
        if receipt['case_id'] is not None:
            return int(receipt['case_id'])
        intent = json.loads(receipt['evidence_json'])
        verified = await self.port.applied(guild.id, receipt['target_user_id'], intent['action'], intent.get('expires_at'), receipt['id'], receipt['created_at'])
        if verified is not True:
            raise ActionFailure('Discord側の実行結果を確定できません。手動照合が必要です。', partial=True)
        return self.repository.add_case(guild.id, receipt['target_user_id'], intent['action'], receipt['reason'],
            receipt['actor_id'], intent.get('expires_at'), False, moderation_event_id=intent.get('parent_event_id'),
            moderation_rule_id=intent.get('rule_id'), source=intent['source'], execution_event_id=receipt['id'], lease=lease)

    async def expire_tempban(self, guild: GuildRef, pending: dict[str, Any]) -> None:
        lease = ResourceLease(self.repository.database_url, 'moderation_member', f"{guild.id}:{pending['user_id']}")
        async def expire(owned):
            receipt = self.repository.expiring_tempban(pending, lease=owned)
            if receipt is None:
                return  # A newer ban/unban intent superseded this temporary sanction.
            applied = await self.port.applied(guild.id, pending['user_id'], 'tempban',
                receipt['expires_at'], receipt['id'], receipt['created_at'])
            if applied is False:
                return  # Absent or replaced, including human bans: never undo it.
            if applied is not True:
                raise ActionFailure('一時Banの所有権を確認できません。手動照合が必要です。', partial=True)
            owned.renew()
            # Recheck the queue claim after the asynchronous audit/state lookup.
            if self.repository.expiring_tempban(pending, lease=owned) is None:
                return
            await self.port.unban(guild.id, pending['user_id'], '一時Banの期限切れ')
            owned.check()
        try:
            await lease.run(expire)
        except LostLease as exc:
            raise ActionFailure(str(exc), retry=True, partial=True) from exc

    async def warn(self, guild: GuildRef, member: MemberRef, reason: str | None, moderator_id: int | None,
                   *, notify: bool | None = None, actor: MemberRef | None = None, execution_key: str | None = None) -> int:
        if actor is not None:
            error = self.manageable(actor, member, "timeout")
            if error:
                raise PermissionError(error)
        module = self.guild_settings.get_module(guild.id, "moderation")["settings"]
        should_notify = bool(module.get("dm_notify")) if notify is None else notify
        dm_sent = await self.dm(member, f"{guild.name}で警告を受けました。理由: {reason or 'なし'}") if should_notify else False
        result = self.repository.add_points_case(guild.id, member.id, 1, reason, moderator_id=moderator_id,
            dm_sent=dm_sent, source='manual', execution_key=execution_key or uuid.uuid4().hex,
            thresholds=self._point_thresholds(guild.id))
        case_id, after = result['case_id'], result['after']
        await self.log_manual(guild, f"Moderation Case #{case_id}", f"`warn` ({after}pt): {member} ({member.id})\n理由: {reason or 'なし'}", category="warning")
        return after

    def _point_thresholds(self, guild_id):
        module = self.guild_settings.get_module(guild_id, 'infractions')
        return module['settings'].get('point_thresholds', []) if module['enabled'] else []

    async def execute_threshold(self, guild: GuildRef, request: dict[str, Any]) -> dict[str, Any]:
        intent = self.repository.threshold_intent(request['id'])
        if intent is None or intent['guild_id'] != guild.id:
            raise PermissionError('閾値処置の保存済みIntentを確認できません。')
        if not self.guild_settings.module_enabled(guild.id, 'moderation') or not self.guild_settings.module_enabled(guild.id, 'infractions'):
            raise PermissionError('ModerationまたはInfractionsが無効です。')
        action = intent['threshold']['action']
        case_id = await self.apply_case(guild, MemberRef(intent['user_id'], guild.id), action['type'],
            f"{intent['reason'] or '警告ポイント'}: {intent['after']}ポイントに到達", duration_minutes=int(action.get('duration_minutes', 0)),
            notify=False, moderation_event_id=intent.get('parent_event_id'), moderation_rule_id=intent.get('rule_id'),
            source='infraction', execution_key=f"threshold:{intent['event_id']}")
        return {'type': 'threshold', 'status': 'success', 'case_id': case_id}

    @staticmethod
    def _message_template(text: str, member: MemberRef | None, reason: str, *, guild: GuildRef | None = None,
                          channel: ChannelRef | None = None, rule: dict[str, Any] | None = None) -> str:
        values = {
            "user": member.mention if member else "不明",
            "username": member.name if member else "不明",
            "reason": reason,
            "server": guild.name if guild else "不明",
            "channel": getattr(channel, "mention", getattr(channel, "name", "不明")),
            "rule": str((rule or {}).get("name") or "不明"),
        }
        rendered = text
        for name, value in values.items():
            rendered = rendered.replace(f"{{{name}}}", str(value))
        return rendered[:2000]

    @staticmethod
    def _overwrite_value(value: bool | None) -> bool | None:
        return value if value in {True, False} else None

    async def lockdown(self, guild: GuildRef, reason: str, duration_minutes: int, *, started_by: int | None = None,
            source_event_id: int | None = None, channel_ids: list[int] | None = None, category_ids: list[int] | None = None) -> int:
        lease = ResourceLease(self.repository.database_url, 'moderation_lockdown', guild.id)
        try:
            return await lease.run(lambda owned: self._lockdown_owned(guild, reason, duration_minutes,
                started_by, source_event_id, channel_ids, category_ids, owned))
        except LostLease as exc:
            raise ActionFailure(str(exc), retry=True, partial=True) from exc

    async def _lockdown_owned(self, guild, reason, duration_minutes, started_by, source_event_id, channel_ids, category_ids, lease):
        if self.repository.active_lockdown(guild.id):
            raise ActionFailure('An active lockdown must be restored before starting another', partial=True)
        snapshots = self.port.lockdown_snapshots(guild.id, channel_ids or [], category_ids or [])
        for snapshot in snapshots:
            snapshot['before'] = await self.port.fresh_overwrite(guild.id, snapshot['channel_id'], snapshot['role_id'])
        unlock_at = int(time.time()) + max(1, min(duration_minutes, 1440)) * 60
        lockdown_id = self.repository.start_lockdown(guild.id, reason=reason, started_by=started_by, unlock_at=unlock_at, source_event_id=source_event_id, lease=lease)
        for snapshot in snapshots:
            # Recovery intent must exist before changing Discord permissions.
            self.repository.save_lockdown_snapshot(lockdown_id, snapshot['channel_id'], snapshot['role_id'], snapshot['before'], snapshot['applied'], lease=lease)
        try:
            for snapshot in snapshots:
                lease.renew()
                await self.port.set_overwrite(guild.id, snapshot['channel_id'], snapshot['role_id'], snapshot['applied'], f'Moderation lockdown #{lockdown_id}: {reason}')
            self.repository.set_raid_state(guild.id, True, lockdown_id=lockdown_id, lease=lease)
        except Exception as exc:
            self.repository.finish_lockdown(lockdown_id, error=str(exc), lease=lease)
            raise
        return lockdown_id

    async def unlock_lockdown(self, guild: GuildRef, lockdown_id: int | None = None) -> dict[str, int]:
        lease = ResourceLease(self.repository.database_url, 'moderation_lockdown', guild.id)
        try:
            return await lease.run(lambda owned: self._unlock_owned(guild, lockdown_id, owned))
        except LostLease as exc:
            raise ActionFailure(str(exc), retry=True, partial=True) from exc

    async def _unlock_owned(self, guild, lockdown_id, lease):
        active = self.repository.active_lockdown(guild.id)
        if not active or lockdown_id and int(active['id']) != lockdown_id:
            return {'restored': 0, 'conflicts': 0}
        restored = conflicts = 0
        for snapshot in self.repository.lockdown_snapshots(int(active['id'])):
            lease.renew()
            try:
                current = await self.port.fresh_overwrite(guild.id, snapshot['channel_id'], snapshot['role_id'])
            except Exception as exc:
                self.repository.finish_lockdown(int(active['id']), error=str(exc), lease=lease)
                raise
            if current == snapshot['before']:
                restored += 1
                continue
            if current != snapshot['applied']:
                conflicts += 1
                continue
            try:
                await self.port.set_overwrite(guild.id, snapshot['channel_id'], snapshot['role_id'], snapshot['before'], f"Moderation lockdown #{active['id']} ended")
            except Exception as exc:
                self.repository.finish_lockdown(int(active['id']), error=str(exc), lease=lease)
                raise
            restored += 1
        if not conflicts:
            self.repository.finish_lockdown(int(active['id']), lease=lease)
        else:
            self.repository.finish_lockdown(int(active['id']), error=f'{conflicts} permission conflicts require review', lease=lease)
        return {'restored': restored, 'conflicts': conflicts}

    async def execute_actions(self, context: ActionContext, rule: dict[str, Any], reason: str, event_id: int,
            settings: dict[str, Any]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        member, message, guild = context.member, context.message, context.guild
        for sequence, action in enumerate(rule.get("actions", [])):
            action_type = action["type"]
            if rule.get("mode") == "monitor":
                results.append({"type": action_type, "status": "simulated"})
                continue
            try:
                if action_type in {"delete", "purge", "remove_reaction", "lock", "unlock"}:
                    detail = await self.port.perform(context, action, reason)
                    results.append({"type": action_type, "status": "success", **detail})
                elif action_type == "points":
                    if member is None:
                        raise ValueError("対象メンバーが見つかりません")
                    expiry_days = int(action.get("expires_days", 30))
                    expires_at = int(time.time()) + expiry_days * 86400 if expiry_days else None
                    result = self.repository.add_points_case(guild.id, member.id, int(action.get('points', 1)), reason,
                        moderation_rule_id=rule.get('id'), moderation_event_id=event_id, expires_at=expires_at,
                        source=rule.get('family', 'automod'), execution_key=f'event:{event_id}:{sequence}',
                        thresholds=self._point_thresholds(guild.id))
                    results.append({'type': action_type, 'status': 'success', 'case_id': result['case_id'],
                        'before': result['before'], 'after': result['after']})
                    if result.get('request_id'):
                        results.append({'type': 'threshold', 'status': 'queued', 'request_id': result['request_id']})
                elif action_type == "notify":
                    channel_id = int(action['channel_id']) if action.get('channel_id') else context.channel.id if context.channel else None
                    if channel_id is None:
                        raise ValueError('通知チャンネルが見つかりません')
                    text = action.get('message', 'ルール違反を検知しました。')
                    if member:
                        text = self._message_template(text, member, reason, guild=guild, channel=ChannelRef(channel_id), rule=rule)
                    await self.port.send(channel_id, content=text[:2000])
                    results.append({"type": action_type, "status": "success"})
                elif action_type == "dm":
                    if member is None:
                        raise ValueError("対象メンバーが見つかりません")
                    sent = await self.dm(member, self._message_template(action.get("message", "ルール違反を検知しました: {reason}"), member, reason, guild=guild, channel=context.channel, rule=rule))
                    results.append({"type": action_type, "status": "success" if sent else "failed"})
                elif action_type in {"timeout", "untimeout", "kick", "ban", "unban", "tempban", "softban"}:
                    if member is None:
                        raise ValueError("対象メンバーが見つかりません")
                    case_id = await self.apply_case(guild, member, action_type, reason, None, int(action.get("duration_minutes", 0)), False,
                        moderation_event_id=event_id, moderation_rule_id=rule.get("id"), source=rule.get("family", "automod"),
                        actor=context.actor if rule.get("family") == "infraction" else None)
                    results.append({"type": action_type, "status": "success", "case_id": case_id})
                elif action_type == "lockdown":
                    lockdown_id = await self.lockdown(guild, reason, int(action.get("duration_minutes", 30)), source_event_id=event_id,
                        channel_ids=action.get("channel_ids"), category_ids=action.get("category_ids"))
                    results.append({"type": action_type, "status": "success", "lockdown_id": lockdown_id})
                elif action_type == "unlockdown":
                    result = await self.unlock_lockdown(guild)
                    results.append({"type": action_type, "status": "failed" if result['conflicts'] else "success", **result})
                elif action_type == "log":
                    results.append({"type": action_type, "status": "success"})
            except (ValueError, PermissionError, ActionFailure) as exc:
                results.append({"type": action_type, "status": "failed", "error": str(exc)[:300],
                    "retry": bool(getattr(exc, 'retry', False)), "partial": bool(getattr(exc, 'partial', False))})
        return results

    async def log_event(self, context: ActionContext, rule: dict[str, Any], event_id: int, reason: str,
            results: list[dict[str, Any]], settings: dict[str, Any]) -> None:
        logs = self.guild_settings.get_module(context.guild.id, 'moderation_logs')
        family = str(rule.get('family', 'automod'))
        category = family if family in {'automod', 'anti_spam', 'anti_raid'} else 'admin'
        if not logs['enabled'] or not logs['settings'].get(f'log_{category}', False):
            return
        channel_id = self._log_channel(context.guild, settings)
        if channel_id is None:
            return
        rendered = ', '.join(f"{item.get('type')}: {item.get('status')}" for item in results) or '記録のみ'
        log_action = next((action for action in rule.get('actions', []) if action.get('type') == 'log'), None)
        description = self._message_template(str((log_action or {}).get('message') or '{reason}'), context.member, reason,
            guild=context.guild, channel=context.channel, rule=rule)
        fields = [{'name': '機能 / ルール', 'value': f"{rule.get('family')} / {rule.get('name')} (`{rule.get('trigger_type')}`)", 'inline': False}]
        if context.member:
            fields.append({'name': '対象', 'value': f'{context.member} ({context.member.id})', 'inline': False})
        if context.channel:
            fields.append({'name': 'チャンネル', 'value': f'#{context.channel.name} ({context.channel.id})', 'inline': False})
        fields.append({'name': '実行結果', 'value': rendered[:1024], 'inline': False})
        try:
            await self.port.send(channel_id, embed={'title': f'Moderation Event #{event_id}', 'description': description[:4000],
                'color': 0xf1c40f if rule.get('mode') == 'monitor' else 0xe74c3c, 'fields': fields})
        except ActionFailure:
            LOGGER.warning('Could not write Moderation log', exc_info=True)
