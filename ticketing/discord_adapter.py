"""Ticket container permissions and Discord resource creation."""
import discord

from discord_io import DiscordFailure
from .contracts import ContainerRef
from .messages import bounded_embed


class DiscordTicketAdapter:
    def __init__(self, bot):
        self.bot = bot
        self._created = {}

    def container(self, resource_id):
        return self._created.pop(resource_id, None) or self.bot.get_channel(resource_id)

    async def find_container(self, ticket, panel):
        guild = self.bot.get_guild(ticket['guild_id'])
        if guild is None:
            raise DiscordFailure('Ticket guild unavailable', retry=True)
        try:
            if panel['mode'] == 'channel':
                matches = [channel for channel in guild.text_channels if channel.topic == f'Tueka ticket:{ticket["id"]}']
            else:
                matches = [thread for thread in await guild.active_threads()
                    if thread.name.endswith(f'-t{ticket["id"]}') and thread.parent_id == panel['thread_parent_channel_id']
                    and thread.owner_id == self.bot.user.id and thread.is_private()]
            if len(matches) != 1:
                raise DiscordFailure('Ticket creation receipt needs manual reconciliation', partial=True)
            return await self.recover_container(ticket, panel, matches[0].id)
        except discord.HTTPException as exc:
            raise DiscordFailure(str(exc), retry=exc.status == 429 or exc.status >= 500, partial=True) from exc

    async def recover_container(self, ticket, panel, resource_id):
        guild = self.bot.get_guild(ticket['guild_id'])
        channel = guild.get_channel_or_thread(resource_id) if guild else None
        member = guild.get_member(ticket['opener_id']) if guild else None
        if channel is None or member is None:
            raise DiscordFailure('Orphan resource or opener unavailable', retry=True, resource_id=resource_id)
        try:
            if isinstance(channel, discord.TextChannel) and panel['mode'] == 'channel':
                if channel.topic != f'Tueka ticket:{ticket["id"]}':
                    raise DiscordFailure('Orphan identity requires manual review', partial=True, resource_id=resource_id)
                if channel.overwrites_for(guild.default_role).view_channel is not False or channel.overwrites_for(member).view_channel is not True:
                    raise DiscordFailure('Orphan permissions changed; manual review required', partial=True, resource_id=resource_id)
                return ContainerRef(channel.id, channel.category_id)
            if isinstance(channel, discord.Thread) and panel['mode'] == 'private_thread' and channel.is_private():
                if channel.parent_id != int(panel['thread_parent_channel_id']):
                    raise DiscordFailure('Orphan thread parent changed', partial=True, resource_id=resource_id)
                await channel.add_user(member)
                return ContainerRef(channel.id, channel.parent_id)
            raise DiscordFailure('Orphan resource mode mismatch', partial=True, resource_id=resource_id)
        except discord.HTTPException as exc:
            raise DiscordFailure(str(exc), retry=exc.status == 429 or exc.status >= 500, resource_id=resource_id) from exc

    async def create_container(self, ticket, panel, name, team_roles, on_call, team_users=None):
        guild = self.bot.get_guild(ticket['guild_id'])
        member = guild.get_member(ticket['opener_id']) if guild else None
        if guild is None or member is None or guild.me is None:
            raise DiscordFailure('Ticket guild/member unavailable', retry=True)
        container = None
        try:
            if panel['mode'] == 'channel':
                category = guild.get_channel(int(panel['category_id']))
                if not isinstance(category, discord.CategoryChannel):
                    raise ValueError('category')
                overwrites = {
                    guild.default_role: discord.PermissionOverwrite(view_channel=False),
                    member: discord.PermissionOverwrite(view_channel=True, send_messages=True, read_message_history=True, **panel['creator_permissions']),
                    guild.me: discord.PermissionOverwrite(view_channel=True, send_messages=True, manage_channels=True, manage_messages=True, read_message_history=True),
                }
                for role_id in team_roles:
                    role = guild.get_role(int(role_id))
                    if role:
                        overwrites[role] = discord.PermissionOverwrite(view_channel=True, send_messages=panel['claim_mode'] == 'shared_reply', read_message_history=True, manage_messages=True)
                container = await guild.create_text_channel(name, category=category, overwrites=overwrites,
                    topic=f'Tueka ticket:{ticket["id"]}', reason=f'Tueka ticket:{ticket["id"]}')
                parent_id = container.category_id
            else:
                parent = guild.get_channel(int(panel['thread_parent_channel_id']))
                if not isinstance(parent, discord.TextChannel):
                    raise ValueError('thread_parent')
                container = await parent.create_thread(name=f"{name[:75]}-t{ticket['id']}", type=discord.ChannelType.private_thread, invitable=False,
                    reason=f'Tueka ticket:{ticket["id"]}')
                self._created[container.id] = container
                await container.add_user(member)
                for user_id in on_call:
                    staff = guild.get_member(user_id)
                    if staff and (user_id in (team_users or []) or any(role.id in team_roles for role in staff.roles)):
                        try:
                            await container.add_user(staff)
                        except discord.HTTPException:
                            pass
                parent_id = container.parent_id
            self._created[container.id] = container
            return ContainerRef(container.id, parent_id)
        except discord.HTTPException as exc:
            raise DiscordFailure(str(exc), retry=exc.status == 429 or exc.status >= 500,
                partial=container is not None, resource_id=container.id if container else None) from exc

    def _panel_channel(self, guild_id, channel_id):
        guild = self.bot.get_guild(guild_id)
        channel = guild.get_channel(channel_id) if guild else None
        if not isinstance(channel, discord.TextChannel):
            raise DiscordFailure('Panel channel unavailable', retry=True)
        return channel

    async def delete_panel_message(self, guild_id, channel_id, message_id):
        try:
            channel = self._panel_channel(guild_id, channel_id)
            message = await channel.fetch_message(message_id)
            await message.delete()
        except discord.NotFound:
            return
        except discord.HTTPException as exc:
            raise DiscordFailure(str(exc), retry=exc.status == 429 or exc.status >= 500) from exc

    async def find_panel_message(self, config):
        channel = self._panel_channel(config['guild_id'], config['channel_id'])
        marker = f'Tueka panel:{config["id"]}'
        try:
            async for candidate in channel.history(limit=200):
                if candidate.author.id == self.bot.user.id and any(e.footer.text == marker for e in candidate.embeds):
                    return candidate.id
        except discord.HTTPException as exc:
            raise DiscordFailure(str(exc), retry=exc.status == 429 or exc.status >= 500, partial=True) from exc
        raise DiscordFailure('Panel receipt needs reconciliation', partial=True)

    async def publish_panel(self, config, panels, *, recover=False):
        channel = self._panel_channel(config['guild_id'], config['channel_id'])
        marker = f'Tueka panel:{config["id"]}'
        view = discord.ui.View(timeout=None)
        styles = {'primary': discord.ButtonStyle.primary, 'secondary': discord.ButtonStyle.secondary,
                  'success': discord.ButtonStyle.success, 'danger': discord.ButtonStyle.danger}
        for panel in panels:
            button = panel.get('button') or {}
            view.add_item(discord.ui.Button(label=str(button.get('label') or panel['name'])[:80],
                style=styles.get(str(button.get('style')), discord.ButtonStyle.primary),
                emoji=str(button.get('emoji') or '') or None, custom_id=f'tueka-ticket:open:{panel["id"]}'))
        embed = discord.Embed(title=str(config['title'])[:256], description=str(config.get('description') or '')[:4000],
                              color=int(str(config.get('color') or '#5865F2').lstrip('#'), 16))
        embed.set_footer(text=marker)
        if config.get('image_url'):
            embed.set_image(url=str(config['image_url']))
        if config.get('thumbnail_url'):
            embed.set_thumbnail(url=str(config['thumbnail_url']))
        try:
            message = None
            if config.get('message_id') and config.get('message_id') != config.get('previous_message_id'):
                try:
                    message = await channel.fetch_message(int(config['message_id']))
                except discord.NotFound:
                    pass
            if message is None and recover:
                async for candidate in channel.history(limit=200):
                    if candidate.author.id == self.bot.user.id and any(e.footer.text == marker for e in candidate.embeds):
                        message = candidate
                        break
                if message is None:
                    raise DiscordFailure('Panel receipt needs reconciliation', partial=True)
            values = dict(content=str(config.get('content') or '') or None, embed=embed, view=view,
                          allowed_mentions=discord.AllowedMentions.none())
            message = await message.edit(**values) if message else await channel.send(**values)
            return message.id
        except discord.HTTPException as exc:
            raise DiscordFailure(str(exc), retry=exc.status == 429 or exc.status >= 500,
                                 partial=recover or exc.status >= 500) from exc

    async def claim_changes(self, ticket, panel, member_id, team_roles):
        guild = self.bot.get_guild(ticket['guild_id'])
        channel = guild.get_channel(ticket['discord_container_id']) if guild else None
        if not isinstance(channel, discord.TextChannel) or ticket['mode'] != 'channel':
            raise DiscordFailure('claim_unavailable')
        changes = {}
        for role_id in team_roles:
            role = guild.get_role(role_id)
            if role:
                visible = panel['claim_mode'] != 'claim_only_view' or member_id is None
                changes[('role', role_id)] = {'view_channel': visible, 'send_messages': panel['claim_mode'] == 'shared_reply',
                    'read_message_history': visible, 'manage_messages': visible}
        if ticket.get('claimed_by') and ticket['claimed_by'] != member_id:
            changes[('member', ticket['claimed_by'])] = None
        if member_id:
            if guild.get_member(member_id) is None:
                raise DiscordFailure('Claimant unavailable', retry=True)
            changes[('member', member_id)] = {'view_channel': True, 'send_messages': True,
                'read_message_history': True, 'manage_messages': True}
        result = []
        for (kind, identity), after in changes.items():
            subject = guild.get_role(identity) if kind == 'role' else guild.get_member(identity)
            if subject is not None:
                before = dict(channel.overwrites_for(subject)) if subject in channel.overwrites else None
                if after is not None:
                    after = {**(before or {}), **after}
                result.append({'kind': kind, 'id': identity, 'before': before, 'after': after})
        return result

    async def permission(self, ticket, change, *, restore=False):
        guild = self.bot.get_guild(ticket['guild_id'])
        channel = guild.get_channel(ticket['discord_container_id']) if guild else None
        subject = (guild.get_role(change['id']) if change['kind'] == 'role' else guild.get_member(change['id'])) if guild else None
        if not isinstance(channel, discord.TextChannel) or subject is None:
            raise DiscordFailure('Permission target unavailable', retry=True)
        current = dict(channel.overwrites_for(subject)) if subject in channel.overwrites else None
        desired, expected = (change['before'], change['after']) if restore else (change['after'], change['before'])
        # Normalize unspecified permissions before comparing API snapshots.
        clean = lambda value: {key: val for key, val in (value or {}).items() if val is not None}
        if clean(current) == clean(desired):
            return
        if clean(current) != clean(expected):
            raise DiscordFailure('Ticket permission conflict requires review', partial=True)
        overwrite = discord.PermissionOverwrite(**desired) if desired is not None else None
        try:
            await channel.set_permissions(subject, overwrite=overwrite, reason='Ticket claim recovery' if restore else 'Ticket claim updated')
        except discord.HTTPException as exc:
            raise DiscordFailure(str(exc), retry=exc.status == 429 or exc.status >= 500) from exc

    async def set_closed(self, ticket, *, closed):
        guild = self.bot.get_guild(ticket['guild_id'])
        if guild is None:
            raise DiscordFailure('Ticket guild unavailable', retry=True)
        channel = guild.get_channel_or_thread(ticket['discord_container_id'])
        if channel is None:
            try:
                channel = await self.bot.fetch_channel(ticket['discord_container_id'])
            except discord.NotFound:
                if closed:
                    return
                raise DiscordFailure('Ticket thread missing', missing=True)
            except discord.HTTPException as exc:
                raise DiscordFailure(str(exc), retry=exc.status == 429 or exc.status >= 500) from exc
        if channel.guild.id != ticket['guild_id']:
            raise DiscordFailure('Ticket guild mismatch')
        try:
            if isinstance(channel, discord.Thread):
                await channel.edit(archived=closed, locked=closed, reason='Ticket closed' if closed else 'Ticket reopened')
            elif isinstance(channel, discord.TextChannel) and closed:
                await channel.delete(reason='Ticket closed and transcript saved')
            else:
                raise DiscordFailure('reopen_unavailable')
        except discord.NotFound:
            if not closed:
                raise DiscordFailure('Ticket thread missing', missing=True)
        except discord.HTTPException as exc:
            raise DiscordFailure(str(exc), retry=exc.status == 429 or exc.status >= 500) from exc

    async def history(self, ticket):
        guild = self.bot.get_guild(ticket['guild_id'])
        channel = guild.get_channel_or_thread(ticket['discord_container_id']) if guild else None
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            raise DiscordFailure('Ticket history unavailable', retry=True)
        try:
            async for message in channel.history(limit=None, oldest_first=True):
                yield message
        except discord.HTTPException as exc:
            raise DiscordFailure(str(exc), retry=exc.status == 429 or exc.status >= 500) from exc

    async def read_attachment(self, attachment):
        try:
            return await attachment.read(use_cached=True)
        except discord.HTTPException as exc:
            if exc.status in {404, 415}:
                try:
                    return await attachment.read(use_cached=False)
                except discord.HTTPException as source_error:
                    exc = source_error
            raise DiscordFailure(str(exc), retry=exc.status == 429 or exc.status >= 500) from exc

    async def participant(self, ticket, user_id, *, add):
        guild = self.bot.get_guild(ticket['guild_id'])
        if guild is None:
            raise DiscordFailure('Ticket guild unavailable', retry=True)
        channel = guild.get_channel_or_thread(ticket['discord_container_id'])
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            raise DiscordFailure('Ticket channel unavailable', retry=True)
        member = guild.get_member(user_id)
        try:
            if member is None:
                try:
                    member = await guild.fetch_member(user_id)
                except discord.NotFound:
                    if not add:
                        return
                    raise DiscordFailure('Member unavailable', missing=True)
            if isinstance(channel, discord.Thread):
                if add:
                    await channel.add_user(member)
                else:
                    await channel.remove_user(member)
            elif add:
                overwrite = channel.overwrites_for(member)
                overwrite.update(view_channel=True, send_messages=True, read_message_history=True)
                await channel.set_permissions(member, overwrite=overwrite, reason='Ticket participant added')
            else:
                await channel.set_permissions(member, overwrite=None, reason='Ticket participant removed')
        except discord.HTTPException as exc:
            raise DiscordFailure(str(exc), retry=exc.status == 429 or exc.status >= 500) from exc

    async def rename(self, ticket, name):
        guild = self.bot.get_guild(ticket['guild_id'])
        channel = guild.get_channel_or_thread(ticket['discord_container_id']) if guild else None
        if not isinstance(channel, (discord.TextChannel, discord.Thread)):
            raise DiscordFailure('Ticket channel unavailable', retry=True)
        try:
            await channel.edit(name=name[:100], reason='Ticket renamed')
        except discord.HTTPException as exc:
            raise DiscordFailure(str(exc), retry=exc.status == 429 or exc.status >= 500) from exc

    async def notes_thread(self, ticket, *, recover):
        guild = self.bot.get_guild(ticket['guild_id'])
        if guild is None:
            raise DiscordFailure('Ticket guild unavailable', retry=True)
        try:
            if ticket.get('notes_thread_id'):
                thread = await self.bot.fetch_channel(ticket['notes_thread_id'])
                if not isinstance(thread, discord.Thread) or thread.guild.id != guild.id or thread.parent_id != ticket['discord_container_id'] or not thread.is_private():
                    raise DiscordFailure('Notes thread identity conflict', partial=True)
                return thread.id
            name = f'staff-notes-{ticket["ticket_number"]}-{ticket["id"]}'
            if recover:
                matches = [thread for thread in await guild.active_threads()
                    if thread.name == name and thread.parent_id == ticket['discord_container_id'] and thread.owner_id == self.bot.user.id and thread.is_private()]
                if len(matches) == 1:
                    return matches[0].id
                raise DiscordFailure('Notes thread receipt needs reconciliation', partial=True)
            channel = guild.get_channel(ticket['discord_container_id'])
            if not isinstance(channel, discord.TextChannel):
                raise DiscordFailure('Ticket notes parent unavailable')
            thread = await channel.create_thread(name=name, type=discord.ChannelType.private_thread, invitable=False,
                                                 reason=f'Tueka notes:{ticket["id"]}')
            return thread.id
        except discord.HTTPException as exc:
            raise DiscordFailure(str(exc), retry=exc.status == 429 or exc.status >= 500,
                                 partial=recover or exc.status >= 500) from exc

    async def send_reply(self, ticket, delivery_key, content, *, recover):
        guild = self.bot.get_guild(ticket['guild_id'])
        if guild is None:
            raise DiscordFailure('Ticket guild unavailable', retry=True)
        marker = f'Tueka ticket delivery:{delivery_key}'
        try:
            channel = guild.get_channel_or_thread(ticket['discord_container_id'])
            if channel is None:
                channel = await self.bot.fetch_channel(ticket['discord_container_id'])
            if not isinstance(channel, (discord.TextChannel, discord.Thread)) or channel.guild.id != guild.id:
                raise DiscordFailure('Ticket channel unavailable')
            if recover:
                async for message in channel.history(limit=200):
                    if message.author.id == self.bot.user.id and any(e.footer.text == marker for e in message.embeds):
                        return {'id': message.id, 'created_at': int(message.created_at.timestamp())}
                raise DiscordFailure('Ticket message receipt needs reconciliation', partial=True)
            embed = discord.Embed()
            embed.set_footer(text=marker)
            if len(content) > 2000:
                heading, separator, body = content.partition('\n')
                if separator and heading.startswith('**') and heading.endswith('**') and len(body) <= 2000:
                    embed.set_author(name=heading[2:-2])
                    content = body
                else:
                    embed.description = content
                    content = None
            message = await channel.send(content=content, embed=embed, allowed_mentions=discord.AllowedMentions.none())
            return {'id': message.id, 'created_at': int(message.created_at.timestamp())}
        except discord.HTTPException as exc:
            raise DiscordFailure(str(exc), retry=exc.status == 429 or exc.status >= 500,
                                 partial=recover or exc.status >= 500) from exc

    def _ticket_text_channel(self, ticket):
        guild = self.bot.get_guild(ticket['guild_id'])
        channel = guild.get_channel(ticket['discord_container_id']) if guild else None
        if not isinstance(channel, discord.TextChannel):
            raise DiscordFailure('Ticket text channel unavailable', retry=True)
        return channel

    async def category(self, ticket):
        return self._ticket_text_channel(ticket).category_id

    async def move_category(self, ticket, target, *, expected):
        channel = self._ticket_text_channel(ticket)
        if channel.category_id == target:
            return
        if channel.category_id != expected:
            raise DiscordFailure('Ticket category changed; review required', partial=True)
        category = channel.guild.get_channel(target) if target else None
        if target and not isinstance(category, discord.CategoryChannel):
            raise DiscordFailure('Ticket category unavailable')
        try:
            await channel.edit(category=category, reason='Ticket response state changed')
        except discord.HTTPException as exc:
            raise DiscordFailure(str(exc), retry=exc.status == 429 or exc.status >= 500) from exc

    async def member_identity(self, ticket):
        guild = self.bot.get_guild(ticket['guild_id'])
        if guild is None:
            raise DiscordFailure('Ticket guild unavailable', retry=True)
        member = guild.get_member(ticket['opener_id'])
        try:
            member = member or await guild.fetch_member(ticket['opener_id'])
        except discord.HTTPException as exc:
            raise DiscordFailure(str(exc), retry=exc.status == 429 or exc.status >= 500) from exc
        return {'id': member.id, 'name': member.name}

    async def notice(self, ticket, key, packet, *, recover):
        marker = f'Tueka ticket notice:{key}'
        try:
            if packet.get('user_id'):
                user = await self.bot.fetch_user(packet['user_id'])
                channel = user.dm_channel or await user.create_dm()
            else:
                guild = self.bot.get_guild(ticket['guild_id'])
                if guild is None:
                    raise DiscordFailure('Ticket guild unavailable', retry=True)
                channel = guild.get_channel_or_thread(packet['channel_id']) or await self.bot.fetch_channel(packet['channel_id'])
                if channel.guild.id != ticket['guild_id']:
                    raise DiscordFailure('Ticket notice guild mismatch')
            if recover:
                async for message in channel.history(limit=200):
                    if message.author.id == self.bot.user.id and any((e.footer.text or '').endswith(marker) for e in message.embeds):
                        return {'id': message.id, 'created_at': int(message.created_at.timestamp())}
                raise DiscordFailure('Ticket notice receipt needs reconciliation', partial=True)
            embed_data = dict(packet.get('embed') or {})
            footer = (packet.get('embed') or {}).get('footer') or {}
            embed_data['footer'] = {'text': (str(footer.get('text') or '')[:1900] + ' · ' + marker).lstrip(' ·')}
            if footer.get('icon_url'):
                embed_data['footer']['icon_url'] = footer['icon_url']
            embed = discord.Embed.from_dict(bounded_embed(embed_data))
            view = discord.ui.View(timeout=None)
            for button in packet.get('buttons', []):
                view.add_item(discord.ui.Button(**{**button, 'style': discord.ButtonStyle(button.get('style', 2))}))
            message = await channel.send(content=packet.get('content'), embed=embed, view=view,
                allowed_mentions=discord.AllowedMentions(everyone=False,
                    users=[discord.Object(id=identity) for identity in packet.get('user_ids', [])],
                    roles=[discord.Object(id=identity) for identity in packet.get('role_ids', [])]))
            return {'id': message.id, 'created_at': int(message.created_at.timestamp())}
        except discord.HTTPException as exc:
            raise DiscordFailure(str(exc), retry=exc.status == 429 or exc.status >= 500,
                                 partial=recover or exc.status >= 500) from exc

    async def remove_open_mentions(self, ticket, message_id):
        channel = self.container(ticket['discord_container_id'])
        try:
            channel = channel or await self.bot.fetch_channel(ticket['discord_container_id'])
            if channel.guild.id != ticket['guild_id']:
                raise DiscordFailure('Ticket guild mismatch')
            message = await channel.fetch_message(message_id)
            await message.edit(content=None, allowed_mentions=discord.AllowedMentions.none())
        except discord.HTTPException as exc:
            raise DiscordFailure(str(exc), retry=exc.status == 429 or exc.status >= 500) from exc

    async def delete_resource(self, ticket):
        guild = self.bot.get_guild(ticket['guild_id'])
        if guild is None:
            raise DiscordFailure('Ticket guild unavailable', retry=True)
        try:
            channel = guild.get_channel_or_thread(ticket['discord_container_id']) or await self.bot.fetch_channel(ticket['discord_container_id'])
            if channel.guild.id != guild.id:
                raise DiscordFailure('Ticket guild mismatch')
            await channel.delete(reason='Ticket deleted from dashboard')
        except discord.NotFound:
            return
        except discord.HTTPException as exc:
            raise DiscordFailure(str(exc), retry=exc.status == 429 or exc.status >= 500) from exc
