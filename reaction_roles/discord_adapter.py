"""Reaction Role message and member-role I/O."""
import discord
from datetime import datetime, timezone

from discord_io import DiscordFailure


class DiscordReactionRoleAdapter:
    def __init__(self, bot):
        self.bot = bot

    async def owns_role_change(self, operation, role_id):
        guild = self.bot.get_guild(operation['guild_id'])
        if guild is None:
            raise DiscordFailure('Guild unavailable', retry=True)
        try:
            async for entry in guild.audit_logs(limit=100, action=discord.AuditLogAction.member_role_update,
                    after=datetime.fromtimestamp(operation['created_at'] - 1, timezone.utc)):
                if getattr(entry.target, 'id', None) != operation['user_id']:
                    continue
                before = {role.id for role in getattr(entry.before, 'roles', [])}
                after = {role.id for role in getattr(entry.after, 'roles', [])}
                if role_id not in before ^ after:
                    continue
                return (getattr(entry.user, 'id', None) == self.bot.user.id and
                        entry.reason in {f'Tueka role operation:{operation["id"]}', f'Tueka role rollback:{operation["id"]}'})
            return False
        except discord.HTTPException as exc:
            raise self._failure(exc) from exc

    async def fetch_message(self, guild_id, channel_id, message_id):
        try:
            return await self._channel(guild_id, channel_id).fetch_message(message_id)
        except discord.HTTPException as exc:
            raise self._failure(exc) from exc

    async def denial_notice(self, user_id, content):
        try:
            user = self.bot.get_user(user_id) or await self.bot.fetch_user(user_id)
            await user.send(content, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException as exc:
            raise self._failure(exc) from exc

    async def log(self, guild_id, channel_id, embed):
        try:
            await self._channel(guild_id, channel_id).send(embed=discord.Embed.from_dict(embed), allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException as exc:
            raise self._failure(exc) from exc

    async def create_channel(self, guild_id, name, actor_id):
        guild = self.bot.get_guild(guild_id)
        if guild is None or guild.me is None or not guild.me.guild_permissions.manage_channels:
            raise DiscordFailure('Bot cannot create channels')
        overwrites = {guild.default_role: discord.PermissionOverwrite(view_channel=True, read_message_history=True, send_messages=False, add_reactions=True),
                      guild.me: discord.PermissionOverwrite(view_channel=True, read_message_history=True, send_messages=True, manage_messages=True, add_reactions=True)}
        try:
            channel = await guild.create_text_channel(name[:100], overwrites=overwrites, reason=f'Reaction Roles channel by {actor_id}')
            return channel.id
        except discord.HTTPException as exc:
            raise self._failure(exc, sending=True) from exc

    def _channel(self, guild_id, channel_id):
        guild = self.bot.get_guild(guild_id)
        channel = guild.get_channel_or_thread(channel_id) if guild else None
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            raise DiscordFailure('message_unavailable', retry=True)
        return channel

    @staticmethod
    def _failure(exc, *, sending=False):
        return DiscordFailure(str(exc), retry=exc.status == 429 or exc.status >= 500,
                              partial=sending and exc.status >= 500, missing=isinstance(exc, discord.NotFound))

    async def publish(self, config, *, recover=False):
        channel = self._channel(config['guild_id'], config['channel_id'])
        marker = f'Tueka reaction-role:{config["id"]}:{config["created_at"]}'
        embed = discord.Embed(title=config['embed']['title'] or None, description=config['embed']['description'] or None,
                              color=int(config['embed']['color'].lstrip('#'), 16))
        embed.set_footer(text=marker)
        try:
            message = None
            if config.get('message_id'):
                try:
                    message = await channel.fetch_message(config['message_id'])
                except discord.NotFound:
                    pass
            if config['source'] == 'external':
                if message is None:
                    raise DiscordFailure('external_message_missing', missing=True)
                return message.id
            if message is None and recover:
                async for candidate in channel.history(limit=200):
                    if candidate.author.id == self.bot.user.id and any(marker == e.footer.text for e in candidate.embeds):
                        message = candidate
                        break
                if message is None:
                    raise DiscordFailure('Publish receipt needs reconciliation', partial=True)
            if message is None:
                message = await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
            else:
                message = await message.edit(embed=embed, allowed_mentions=discord.AllowedMentions.none())
            return message.id
        except discord.HTTPException as exc:
            failure = self._failure(exc, sending=True)
            failure.partial = failure.partial or recover
            raise failure from exc

    async def add_reactions(self, guild_id, channel_id, message_id, emojis, *, foreign=False):
        try:
            message = await self._channel(guild_id, channel_id).fetch_message(message_id)
            for emoji in emojis:
                try:
                    await message.add_reaction(emoji)
                except discord.HTTPException:
                    if not foreign:
                        raise
            return 'bot' if message.author.id == self.bot.user.id else 'external'
        except discord.HTTPException as exc:
            raise self._failure(exc) from exc

    async def delete(self, guild_id, channel_id, message_id):
        try:
            message = await self._channel(guild_id, channel_id).fetch_message(message_id)
            await message.delete()
        except discord.NotFound:
            return
        except discord.HTTPException as exc:
            raise self._failure(exc) from exc

    async def role(self, guild_id, user_id, role_id, *, add, reason):
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            raise DiscordFailure('Guild unavailable', retry=True)
        member, role = guild.get_member(user_id), guild.get_role(role_id)
        # A cache miss is not proof that the member left the guild.
        if member is None:
            try:
                member = await guild.fetch_member(user_id)
            except discord.NotFound:
                if not add:
                    return
                raise DiscordFailure('Member unavailable', missing=True)
            except discord.HTTPException as exc:
                raise self._failure(exc) from exc
        if member is None or role is None:
            if not add:
                return
            raise DiscordFailure('Member or Role unavailable')
        if guild.me is None or not guild.me.guild_permissions.manage_roles or role.managed or role.is_default() or role >= guild.me.top_role:
            raise DiscordFailure('Bot cannot manage this role')
        try:
            if add:
                await member.add_roles(role, reason=reason)
            else:
                await member.remove_roles(role, reason=reason)
        except discord.HTTPException as exc:
            raise self._failure(exc) from exc

    async def member_role_ids(self, guild_id, user_id):
        guild = self.bot.get_guild(guild_id)
        if guild is None:
            raise DiscordFailure('Guild unavailable', retry=True)
        try:
            member = await guild.fetch_member(user_id)
            return {role.id for role in member.roles}
        except discord.HTTPException as exc:
            raise self._failure(exc) from exc

    async def remove_selection(self, guild_id, channel_id, message_id, emoji, user_id):
        try:
            channel = self._channel(guild_id, channel_id)
            message = await channel.fetch_message(message_id)
            await message.remove_reaction(emoji, discord.Object(id=user_id))
        except discord.NotFound:
            return
        except discord.HTTPException as exc:
            raise self._failure(exc) from exc
