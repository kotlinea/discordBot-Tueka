"""Discord objects and API failures terminate at this boundary."""
from datetime import datetime, timedelta, timezone
from typing import Any

import discord

from .contracts import ActionContext, ActionFailure, ChannelRef, GuildRef, MemberRef, MessageRef


def guild_ref(guild) -> GuildRef:
    return GuildRef(guild.id, getattr(guild, 'name', ''))


def member_ref(member, guild_id: int | None = None) -> MemberRef | None:
    if member is None:
        return None
    return MemberRef(member.id, guild_id if guild_id is not None else member.guild.id, getattr(member, 'name', ''))


def action_context(guild, member=None, message=None, channel=None, reaction=None, actor=None) -> ActionContext:
    channel_value = ChannelRef(channel.id, getattr(channel, 'name', '')) if channel else None
    message_value = MessageRef(message.id, ChannelRef(message.channel.id, getattr(message.channel, 'name', ''))) if message else None
    return ActionContext(guild_ref(guild), member_ref(member, guild.id), message_value, channel_value,
                         str(reaction.emoji) if reaction else None, member_ref(actor, guild.id))


def failure(exc: discord.HTTPException, *, partial: bool = False) -> ActionFailure:
    return ActionFailure(str(exc), retry=exc.status == 429 or exc.status >= 500,
                         partial=partial or exc.status >= 500, missing=isinstance(exc, discord.NotFound))


class DiscordModerationAdapter:
    def __init__(self, bot):
        self.bot = bot

    def _guild(self, guild_id):
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            raise ActionFailure('Guild unavailable', retry=True)
        return guild

    def manageable(self, actor: MemberRef | None, target: MemberRef, action: str) -> str | None:
        guild = self._guild(target.guild_id)
        if actor and actor.guild_id != target.guild_id:
            return '実行者のサーバーが一致しません。'
        moderator = guild.get_member(actor.id) if actor else None
        if actor and moderator is None:
            return '実行者を確認できません。'
        permission = {'timeout': 'moderate_members', 'untimeout': 'moderate_members', 'kick': 'kick_members',
                      'ban': 'ban_members', 'tempban': 'ban_members', 'softban': 'ban_members',
                      'unban': 'ban_members'}.get(action)
        if (moderator and moderator.id != guild.owner_id and permission
                and not (getattr(moderator.guild_permissions, 'administrator', False)
                         or getattr(moderator.guild_permissions, permission, False))):
            return '実行者に必要なDiscord権限がありません。'
        if guild.me is None or permission and not (getattr(guild.me.guild_permissions, 'administrator', False)
                or getattr(guild.me.guild_permissions, permission, False)):
            return 'Botに必要なDiscord権限がありません。'
        if action == 'unban':
            return None
        member = guild.get_member(target.id)
        if member is None:
            return '対象メンバーが見つかりません。'
        if actor and target.id == actor.id:
            return '自分自身にはこの処置を実行できません。'
        if target.id == guild.owner_id:
            return 'サーバー所有者にはこの処置を実行できません。'
        if action in {'timeout', 'untimeout'} and member.guild_permissions.administrator:
            return 'Administrator権限を持つメンバーのTimeoutは変更できません。'
        if guild.me is None or member.top_role >= guild.me.top_role:
            return 'Botより同等以上のロールを持つメンバーには実行できません。'
        if moderator and member.top_role >= moderator.top_role and moderator.id != guild.owner_id:
            return '自分より同等以上のロールを持つメンバーには実行できません。'
        return None

    async def dm(self, member: MemberRef, text: str) -> bool:
        target = self._guild(member.guild_id).get_member(member.id)
        if target is None:
            return False
        try:
            await target.send(text[:2000])
            return True
        except discord.HTTPException:
            return False

    async def member_action(self, guild_id, user_id, action, reason, duration_minutes, execution_id):
        reason = f"{(reason or '')[:450]} [Tueka execution:{execution_id}]"
        if action == 'unban':
            await self.unban(guild_id, user_id, reason)
            return
        guild = self._guild(guild_id)
        member = guild.get_member(user_id)
        if member is None:
            raise ActionFailure('Member unavailable')
        partial = False
        try:
            if action == 'timeout':
                await member.timeout(timedelta(minutes=duration_minutes), reason=reason)
            elif action == 'untimeout':
                await member.timeout(None, reason=reason)
            elif action == 'kick':
                await member.kick(reason=reason)
            elif action in {'ban', 'tempban', 'softban'}:
                await guild.ban(member, reason=reason)
                partial = True
                if action == 'softban':
                    await guild.unban(discord.Object(id=user_id), reason=f'Softban: {reason or "なし"}')
            else:
                raise ValueError('Unknown moderation action')
        except discord.HTTPException as exc:
            raise failure(exc, partial=partial) from exc

    async def send(self, channel_id, *, content=None, embed=None):
        channel = self.bot.get_channel(channel_id)
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            raise ActionFailure('Channel unavailable', retry=True)
        try:
            await channel.send(content=content, embed=discord.Embed.from_dict(embed) if embed else None,
                               allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException as exc:
            raise failure(exc) from exc

    async def applied(self, guild_id, user_id, action, expires_at, execution_id, created_at):
        guild = self._guild(guild_id)
        if action not in {'ban', 'tempban', 'timeout', 'untimeout', 'unban'}:
            return None
        try:
            audit_action = discord.AuditLogAction.unban if action == 'unban' else discord.AuditLogAction.ban if action in {'ban', 'tempban'} else discord.AuditLogAction.member_update
            matched = False
            async for entry in guild.audit_logs(limit=100, action=audit_action,
                    after=datetime.fromtimestamp(created_at - 1, timezone.utc)):
                if action in {'ban', 'tempban'} and getattr(entry.target, 'id', None) == user_id:
                    # Only the latest ban for this user can establish current ownership.
                    matched = (getattr(entry.user, 'id', None) == getattr(self.bot.user, 'id', None)
                               and f'[Tueka execution:{execution_id}]' in (entry.reason or ''))
                    if not matched:
                        return False
                    break
                if (getattr(entry.target, 'id', None) == user_id and getattr(entry.user, 'id', None) == getattr(self.bot.user, 'id', None)
                        and f'[Tueka execution:{execution_id}]' in (entry.reason or '')):
                    matched = True
                    break
            if not matched:
                return None
            if action in {'ban', 'tempban', 'unban'}:
                try:
                    ban = await guild.fetch_ban(discord.Object(id=user_id))
                    return action != 'unban' and f'[Tueka execution:{execution_id}]' in (ban.reason or '')
                except discord.NotFound:
                    return action == 'unban'
            member = await guild.fetch_member(user_id)
            until = member.timed_out_until
            if action == 'untimeout':
                return until is None
            return until is not None and expires_at is not None and abs(int(until.timestamp()) - expires_at) <= 5
        except discord.HTTPException as exc:
            raise failure(exc) from exc

    async def perform(self, context, action, reason):
        guild = self._guild(context.guild.id)
        ref = context.channel or (context.message.channel if context.message else None)
        channel = guild.get_channel_or_thread(ref.id) if ref else None
        kind = action['type']
        try:
            if kind in {'delete', 'remove_reaction'}:
                if context.message is None or channel is None:
                    raise ValueError('対象メッセージがありません')
                message = channel.get_partial_message(context.message.id)
                if kind == 'delete':
                    try:
                        await message.delete()
                    except discord.NotFound:
                        pass
                elif context.reaction and context.actor:
                    await message.remove_reaction(context.reaction, discord.Object(id=context.actor.id))
                else:
                    raise ValueError('リアクション情報がありません')
            elif kind == 'purge':
                if not isinstance(channel, discord.TextChannel):
                    raise ValueError('削除対象チャンネルがありません')
                deleted = await channel.purge(limit=int(action.get('count', 10)), check=lambda item: context.member is None or item.author.id == context.member.id)
                return {'count': len(deleted)}
            elif kind in {'lock', 'unlock'}:
                if not isinstance(channel, (discord.TextChannel, discord.ForumChannel)):
                    raise ValueError('対象チャンネルがありません')
                overwrite = channel.overwrites_for(guild.default_role)
                overwrite.send_messages = False if kind == 'lock' else None
                await channel.set_permissions(guild.default_role, overwrite=overwrite, reason=reason)
            elif kind == 'unban' and context.member:
                await self.unban(guild.id, context.member.id, reason)
            else:
                raise ValueError('Unknown Discord action')
            return {}
        except discord.HTTPException as exc:
            raise failure(exc) from exc

    async def unban(self, guild_id, user_id, reason):
        try:
            await self._guild(guild_id).unban(discord.Object(id=user_id), reason=reason)
        except discord.NotFound:
            return  # Already absent: safe after an ACK or DB failure.
        except discord.HTTPException as exc:
            raise failure(exc, partial=exc.status >= 500) from exc

    async def fetch_message(self, guild_id, channel_id, message_id):
        channel = self._guild(guild_id).get_channel_or_thread(channel_id)
        if channel is None:
            raise ActionFailure('Channel unavailable', retry=True)
        try:
            return await channel.fetch_message(message_id)
        except discord.HTTPException as exc:
            raise failure(exc) from exc

    def lockdown_snapshots(self, guild_id, channel_ids, category_ids):
        guild = self._guild(guild_id)
        if guild.me is None or not guild.me.guild_permissions.manage_channels:
            raise PermissionError('Botにチャンネル管理権限がありません。')
        return [{'channel_id': c.id, 'role_id': guild.default_role.id,
                 'before': self.overwrite(guild_id, c.id, guild.default_role.id),
                 'applied': {'send_messages': False, 'send_messages_in_threads': False}}
                for c in guild.channels if isinstance(c, (discord.TextChannel, discord.ForumChannel))
                and (not channel_ids and not category_ids or c.id in channel_ids or c.category_id in category_ids)]

    def overwrite(self, guild_id, channel_id, role_id):
        guild = self._guild(guild_id)
        channel, role = guild.get_channel(channel_id), guild.get_role(role_id)
        if channel is None or role is None or not hasattr(channel, 'overwrites_for'):
            return None
        current = channel.overwrites_for(role)
        return {'send_messages': current.send_messages, 'send_messages_in_threads': current.send_messages_in_threads}

    async def fresh_overwrite(self, guild_id, channel_id, role_id):
        guild = self._guild(guild_id)
        role = guild.get_role(role_id)
        try:
            channel = await guild.fetch_channel(channel_id)
        except discord.HTTPException as exc:
            raise failure(exc) from exc
        if (role is None or getattr(getattr(channel, 'guild', None), 'id', None) != guild_id
                or not isinstance(channel, (discord.TextChannel, discord.ForumChannel))):
            raise ActionFailure('Permission target unavailable')
        current = channel.overwrites_for(role)
        return {'send_messages': current.send_messages, 'send_messages_in_threads': current.send_messages_in_threads}

    async def set_overwrite(self, guild_id, channel_id, role_id, values, reason):
        guild = self._guild(guild_id)
        try:
            channel, role = await guild.fetch_channel(channel_id), guild.get_role(role_id)
            if (role is None or getattr(getattr(channel, 'guild', None), 'id', None) != guild_id
                    or not isinstance(channel, (discord.TextChannel, discord.ForumChannel))):
                raise ActionFailure('Permission target unavailable')
            current = channel.overwrites_for(role)
            for key, value in values.items():
                setattr(current, key, value)
            await channel.set_permissions(role, overwrite=current, reason=reason)
        except discord.HTTPException as exc:
            raise failure(exc) from exc
