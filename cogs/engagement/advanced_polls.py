"""Discord poll inputs; shared rules and persistence live in engagement.polls."""
import asyncio
import io
import logging
import time
import uuid
from datetime import datetime
from weakref import WeakValueDictionary

import discord
from discord import app_commands
from discord.ext import commands, tasks

from engagement.polls.repository import PollRepository
from engagement.polls.models import PollError, duration, normalize, disclose, selection
from engagement.polls.service import Actor, PollService
from engagement.polls.delivery import PollDelivery
from engagement.polls.discord_adapter import DiscordPollAdapter, embed_for, public_view
from guild_settings import GuildSettingsRepository
from jobs import run_batch
from .poll_builder import BuilderView
from .poll_results import ResultView

LOGGER = logging.getLogger(__name__)
MODES = [app_commands.Choice(name=name, value=name) for name in ('anonymous','public','secret_winner','reveal_at_end','blind')]


class BallotView(discord.ui.View):
    def __init__(self, cog, actor, poll, selected=()):
        super().__init__(timeout=300)
        self.cog, self.actor, self.poll = cog, actor, poll
        self.choices = list(selected)
        config = poll['config']
        selector = discord.ui.Select(placeholder='選択肢を選んで確定してください', min_values=0, max_values=config['max_choices'],
            options=[discord.SelectOption(label=f'{i+1}. {option}'[:100], value=str(i), default=i in selected,emoji=config['emojis'][i] or None) for i,option in enumerate(config['options'])])
        async def select(interaction):
            self.choices = [int(value) for value in selector.values]
            await interaction.response.defer()
        selector.callback = select
        self.add_item(selector)
        button = discord.ui.Button(label='投票を確定', style=discord.ButtonStyle.primary)
        async def confirm(interaction):
            try:
                await interaction.response.defer()
                actor = await cog.actor(interaction)
                cog.service.vote(actor, poll['id'], self.choices, poll['message_id'])
                await interaction.edit_original_response(content='投票を保存しました。空の選択は取消として保存します。', view=None, embed=None)
                await cog._sync_poll(poll['message_id'])
            except PollError as exc:
                await cog.failure(interaction, exc)
        button.callback = confirm
        self.add_item(button)

    async def interaction_check(self, interaction):
        return interaction.user.id == self.actor.user_id and interaction.guild_id == self.actor.guild_id


class AdvancedPollsCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.engagement_repository = PollRepository(bot.settings.database_url)
        self.guild_settings = GuildSettingsRepository(bot.settings.database_url)
        self.service = PollService(self.engagement_repository)
        self.delivery = PollDelivery(self.engagement_repository, DiscordPollAdapter(bot))
        self.owner = 'poll-'+uuid.uuid4().hex
        self._poll_locks = WeakValueDictionary()
        self._departure_cursor = (0,0)
        self.close_expired_polls.start()

    def cog_unload(self):
        self.close_expired_polls.cancel()

    async def actor(self, interaction):
        if interaction.guild is None:
            raise PollError('forbidden')
        if interaction.type is discord.InteractionType.application_command and not interaction.response.is_done():
            await interaction.response.defer(ephemeral=True)
        try:
            member = await interaction.guild.fetch_member(interaction.user.id)
        except discord.HTTPException:
            raise PollError('forbidden') from None
        return Actor(interaction.guild.id, member.id, tuple(role.id for role in member.roles),
                     manager=member.guild_permissions.administrator or member.guild_permissions.manage_guild or interaction.guild.owner_id == member.id,
                     bot=member.bot)

    @staticmethod
    async def respond(interaction,*args,**kwargs):
        if interaction.response.is_done():
            return await interaction.followup.send(*args,**kwargs)
        return await interaction.response.send_message(*args,**kwargs)

    async def read_poll(self, interaction, actor, poll_id):
        """Gate every Discord result page on current destination visibility."""
        result=self.service.read(actor,poll_id)
        try:
            channel=await interaction.guild.fetch_channel(int(result['channel_id']))
            if channel.guild.id!=actor.guild_id:raise PollError('forbidden')
            member=await interaction.guild.fetch_member(actor.user_id)
            permissions=channel.permissions_for(member)
            if not permissions.view_channel:raise PollError('forbidden')
            if isinstance(channel,discord.Thread) and channel.is_private() and not permissions.manage_threads:
                await channel.fetch_member(actor.user_id)
        except discord.HTTPException:
            raise PollError('forbidden') from None
        return result

    def validate_config(self,interaction,config):
        if any(interaction.guild.get_role(int(role)) is None for role in config['allowed_roles']+config['denied_roles']):
            raise PollError('invalid')
        for value in config['emojis']:
            parsed=discord.PartialEmoji.from_str(value)
            if parsed.id:
                emoji=self.bot.get_emoji(parsed.id)
                if emoji is None or not emoji.is_usable():raise PollError('invalid')
                if emoji.guild_id!=interaction.guild.id and not interaction.channel.permissions_for(interaction.guild.me).use_external_emojis:
                    raise PollError('invalid')

    async def failure(self, interaction, exc):
        messages = {'invalid':'入力の文字数、選択肢、時刻、公開範囲を確認してください。', 'disabled':'拡張投票は無効です。',
                    'forbidden':'この操作を行う権限がありません。', 'not_found':'この投票は利用できません。',
                    'closed':'この投票は終了しています。', 'ineligible':'この投票の参加条件を満たしていません。',
                    'conflict':'状態が更新されています。詳細を確認して再実行してください。',
                    'privacy_expansion':'投票後に個人情報の公開範囲を広げることはできません。',
                    'ballot_locked':'投票後に質問や選択肢、参加条件を変更することはできません。'}
        message = messages.get(exc.code, '操作を完了できません。投票の状態を確認してください。')
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await self.respond(interaction,message, ephemeral=True)

    @staticmethod
    def _embed(question, options, counts=None, image_url=None):
        config=normalize(dict(question=question, options=options, image_url=image_url))
        return embed_for(dict(config=config,counts=counts or [0]*len(options),weighted_counts=counts or [0]*len(options),status='open'))

    @staticmethod
    def _view(message_id, options, disabled=False):
        return public_view(message_id,normalize(dict(question='投票',options=options)),disabled=disabled)

    async def _create(self, interaction, question, options, *, description='', mode='anonymous', max_choices=1, allowed_role=None, image_url=None, duration_seconds=None, scheduled_at=None):
        actor = await self.actor(interaction)
        choices = [item.strip() for item in options.split('|')]
        values = normalize(dict(question=question, description=description, options=choices, mode=mode, max_choices=max_choices,
                                allowed_roles=[str(allowed_role.id)] if allowed_role else [], image_url=image_url), option_limit=20)
        self.validate_config(interaction,values)
        poll=self.service.create(actor, interaction.channel_id, values, str(interaction.id), scheduled_at=scheduled_at, duration_seconds=duration_seconds)
        if not scheduled_at:
            self.engagement_repository.launch(actor.guild_id,poll['id'],actor.user_id,poll['revision'],principal=actor)
        await self.respond(interaction,f"投票 #{poll['id']} の{'予約' if scheduled_at else '公開'}を受け付けました。/poll-show で状態を確認できます。",ephemeral=True)

    @app_commands.command(description='最大20択の投票を作成します。選択肢は | で区切ります。')
    @app_commands.guild_only()
    @app_commands.choices(mode=MODES)
    async def poll(self, interaction:discord.Interaction, question:str, options:str,
                   duration_minutes:app_commands.Range[int,1,43200]|None=None, image_url:str|None=None,
                   description:str='', max_choices:app_commands.Range[int,1,20]=1,
                   mode:str='anonymous', allowed_role:discord.Role|None=None):
        try:
            await self._create(interaction,question,options,description=description,mode=mode,max_choices=max_choices,
                               allowed_role=allowed_role,image_url=image_url,duration_seconds=duration_minutes*60 if duration_minutes else None)
        except PollError as exc: await self.failure(interaction,exc)

    @app_commands.command(name='poll-time',description='指定した期間の投票を作成します。例: 1d 3h 15m')
    @app_commands.guild_only()
    @app_commands.choices(mode=MODES)
    async def poll_time(self, interaction:discord.Interaction, question:str, options:str, time:str, max_choices:app_commands.Range[int,1,20]=1, mode:str='anonymous'):
        try: await self._create(interaction,question,options,duration_seconds=duration(time),max_choices=max_choices,mode=mode)
        except PollError as exc: await self.failure(interaction,exc)

    @app_commands.command(name='poll-schedule',description='日時指定で投票を予約します。日時にはUTCオフセットが必要です。')
    @app_commands.guild_only()
    async def poll_schedule(self, interaction:discord.Interaction, question:str, options:str, start:str, time:str|None=None):
        try:
            parsed=datetime.fromisoformat(start)
            if parsed.tzinfo is None: raise PollError('invalid')
            await self._create(interaction,question,options,scheduled_at=int(parsed.timestamp()),duration_seconds=duration(time) if time else None)
        except (ValueError,OverflowError) as exc:
            await self.failure(interaction,exc if isinstance(exc,PollError) else PollError('invalid'))

    @app_commands.command(name='poll-show',description='投票の状態と公開範囲に応じた結果を確認します。')
    @app_commands.guild_only()
    async def poll_show(self, interaction:discord.Interaction, poll_id:int, page:app_commands.Range[int,1,5]=1):
        try:
            actor=await self.actor(interaction)
            result=await self.read_poll(interaction,actor,poll_id)
            view=ResultView(self,actor,poll_id);view.page=page-1
            await self.respond(interaction,embed=view.render(result),view=view,ephemeral=True)
        except PollError as exc: await self.failure(interaction,exc)

    @app_commands.command(name='pollbuilder',description='プレビューを見ながら最大25択の投票を作成します。')
    @app_commands.guild_only()
    async def pollbuilder(self, interaction:discord.Interaction, question:str='新しい投票', time:str|None=None):
        try:
            actor=await self.actor(interaction)
            poll=self.service.create(actor,interaction.channel_id,dict(question=question,options=['選択肢 1','選択肢 2']),str(interaction.id),duration_seconds=duration(time) if time else None)
            view=BuilderView(self,actor,poll)
            await self.respond(interaction,content='Createで公開します。各ページの全文は公開後も確認できます。',embed=view.preview(),view=view,ephemeral=True)
        except PollError as exc:await self.failure(interaction,exc)

    @app_commands.command(name='poll-edit',description='投票を編集し、保存前にプレビューを確認します。')
    @app_commands.guild_only()
    async def poll_edit(self, interaction:discord.Interaction, poll_id:int):
        try:
            actor=await self.actor(interaction);self.service.require(actor,'manage')
            poll=self.engagement_repository.get(actor.guild_id,poll_id)
            view=BuilderView(self,actor,poll,editing=True)
            await self.respond(interaction,embed=view.preview(),view=view,ephemeral=True)
        except PollError as exc:await self.failure(interaction,exc)

    @app_commands.command(name='poll-copy',description='設定を複製して票を含まない下書きを作成します。')
    @app_commands.guild_only()
    async def poll_copy(self, interaction:discord.Interaction, poll_id:int):
        try:
            actor=await self.actor(interaction);self.service.require(actor,'manage')
            source=self.engagement_repository.get(actor.guild_id,poll_id)
            poll=self.service.create(actor,interaction.channel_id,source['config'],str(interaction.id))
            view=BuilderView(self,actor,poll)
            await self.respond(interaction,embed=view.preview(),view=view,ephemeral=True)
        except PollError as exc:await self.failure(interaction,exc)

    @app_commands.command(name='poll-list',description='サーバーの投票一覧を確認します。')
    @app_commands.guild_only()
    async def poll_list(self, interaction:discord.Interaction, before:int|None=None):
        try:
            actor=await self.actor(interaction);self.service.require(actor,'view')
            items=self.engagement_repository.items(actor.guild_id,before=before,limit=10)
            await self.respond(interaction,'\n'.join(f"#{p['id']} · {p['status']} · {p['question'][:100]}" for p in items) or '投票はありません。',ephemeral=True)
        except PollError as exc: await self.failure(interaction,exc)

    async def _transition(self, interaction, poll_id, action, time=None):
        actor=await self.actor(interaction)
        poll=self.engagement_repository.get(actor.guild_id,poll_id)
        deadline=int(self.engagement_repository.clock())+duration(time) if time else None
        self.service.transition(actor,poll_id,action,poll['revision'],closes_at=deadline)
        await self.respond(interaction,'投票の状態を更新しました。',ephemeral=True)
        if poll['message_id']: await self._sync_poll(poll['message_id'])

    @app_commands.command(name='poll-close',description='投票を終了します。')
    @app_commands.guild_only()
    async def poll_close(self, interaction:discord.Interaction, poll_id:int):
        try: await self._transition(interaction,poll_id,'close')
        except PollError as exc: await self.failure(interaction,exc)

    @app_commands.command(name='poll-reopen',description='票を保持して投票を再開します。')
    @app_commands.guild_only()
    async def poll_reopen(self, interaction:discord.Interaction, poll_id:int, time:str|None=None):
        try: await self._transition(interaction,poll_id,'reopen',time)
        except PollError as exc: await self.failure(interaction,exc)

    @app_commands.command(name='poll-delete',description='投票を削除し、票を消去します。confirm:trueで確定します。')
    @app_commands.guild_only()
    async def poll_delete(self, interaction:discord.Interaction, poll_id:int, confirm:bool=False):
        if not confirm:
            await self.respond(interaction,'削除するには confirm:true を指定してください。',ephemeral=True);return
        try: await self._transition(interaction,poll_id,'delete')
        except PollError as exc: await self.failure(interaction,exc)

    @app_commands.command(name='poll-move',description='投票を別チャンネルへ移動します。')
    @app_commands.guild_only()
    async def poll_move(self, interaction:discord.Interaction, poll_id:int, channel:discord.TextChannel):
        try:
            actor=await self.actor(interaction);self.service.require(actor,'manage')
            if channel.guild.id != actor.guild_id: raise PollError('invalid')
            poll=self.engagement_repository.get(actor.guild_id,poll_id)
            self.engagement_repository.launch(actor.guild_id,poll_id,actor.user_id,poll['revision'],channel=channel.id,principal=actor)
            await self.respond(interaction,'移動を受け付けました。',ephemeral=True)
        except PollError as exc: await self.failure(interaction,exc)

    @app_commands.command(name='poll-export',description='公開範囲に応じた結果をCSVまたはJSONで取得します。')
    @app_commands.guild_only()
    @app_commands.choices(format=[app_commands.Choice(name='CSV',value='csv'),app_commands.Choice(name='JSON',value='json')])
    async def poll_export(self, interaction:discord.Interaction, poll_id:int, format:str='csv'):
        try:
            data=self.service.export(await self.actor(interaction),poll_id,format)
            if len(data)>8*1024*1024: raise PollError('export_too_large')
            await self.respond(interaction,file=discord.File(io.BytesIO(data),filename=f'poll-{poll_id}.{format}'),ephemeral=True)
        except PollError as exc: await self.failure(interaction,exc)

    async def _sync_poll(self, message_id, message=None):
        lock=self._poll_locks.setdefault(message_id,asyncio.Lock())
        async with lock:
            poll=self.engagement_repository.by_message(message_id)
            if poll is None:return
            self.engagement_repository.display_attempted(message_id)
            enabled=self.guild_settings.module_enabled(poll['guild_id'],'advanced_polls')
            try:
                if message is None:
                    guild=self.bot.get_guild(poll['guild_id'])
                    if guild is None:return
                    channel=guild.get_channel_or_thread(poll['channel_id'])
                    if channel is None:channel=await guild.fetch_channel(poll['channel_id'])
                    if not isinstance(channel,discord.abc.Messageable):return
                    message=await channel.fetch_message(message_id)
                closed=not enabled or poll['status']!='open' or (poll['closes_at'] is not None and poll['closes_at']<=int(time.time()))
                await message.edit(embed=embed_for(disclose(poll),marker='受付停止中（機能が無効）' if not enabled else None),view=public_view(message_id,poll['config'],disabled=closed),allowed_mentions=discord.AllowedMentions.none())
            except discord.NotFound:
                self.engagement_repository.ack_display(message_id,poll['display_revision'],enabled);return
            except discord.HTTPException:return
            self.engagement_repository.ack_display(message_id,poll['display_revision'],enabled)

    @commands.Cog.listener()
    async def on_interaction(self, interaction):
        if interaction.type is not discord.InteractionType.component or interaction.message is None or interaction.guild is None:return
        custom_id=(interaction.data or {}).get('custom_id','')
        if not isinstance(custom_id,str) or not custom_id.startswith(('tueka-poll:','tueka-poll-vote:','tueka-poll-select:','tueka-poll-details:')):return
        try:
            parts=custom_id.split(':');message_id=int(parts[1])
            poll=self.engagement_repository.by_message(message_id)
            if not poll or interaction.message.id!=message_id or poll['guild_id']!=interaction.guild.id:raise PollError('not_found')
            await interaction.response.defer(ephemeral=True,thinking=True)
            actor=await self.actor(interaction)
            if parts[0]=='tueka-poll-details':
                page=int(parts[2]);result=await self.read_poll(interaction,actor,poll['id'])
                view=ResultView(self,actor,poll['id']);view.page=page
                await self.respond(interaction,embed=view.render(result),view=view,ephemeral=True);return
            if parts[0] in ('tueka-poll-vote','tueka-poll-select') or poll['config']['max_choices']>1:
                selected=next((row['choices'] for row in poll['ballots'] if row['user_id']==actor.user_id),[])
                selected=list(selected)
                if parts[0]=='tueka-poll-select':
                    selected=selection([int(value) for value in (interaction.data or {}).get('values',[])],len(poll['options']),poll['config']['max_choices'])
                elif parts[0]=='tueka-poll':
                    index=int(parts[2])
                    if not 0<=index<len(poll['options']):raise PollError('invalid')
                    if index in selected:selected.remove(index)
                    elif len(selected)<poll['config']['max_choices']:selected.append(index)
                    else:raise PollError('invalid')
                await self.respond(interaction,'選択して確定してください。空の選択で取り消せます。\n匿名方式でも重複防止のため内部に利用者IDを保存します。',view=BallotView(self,actor,poll,selected),ephemeral=True);return
            self.service.vote(actor,poll['id'],[int(parts[2])],message_id)
            await interaction.followup.send('投票を保存しました。',ephemeral=True)
            await self._sync_poll(message_id,interaction.message)
        except (ValueError,IndexError) as exc:
            await self.failure(interaction,exc if isinstance(exc,PollError) else PollError('invalid'))

    @tasks.loop(seconds=30)
    async def close_expired_polls(self):
        try:
            self.engagement_repository.close_expired()
            self.engagement_repository.purge_expired()
            self.engagement_repository.enqueue_due()
            await run_batch(self.engagement_repository.jobs,self.owner,self.delivery.deliver,limit=20)
            pending=self.engagement_repository.pending_displays()
        except Exception:
            LOGGER.warning('Could not load pending poll displays',exc_info=True);return
        for message_id in pending:
            try:await self._sync_poll(message_id)
            except Exception:LOGGER.warning('Could not synchronize poll %s',message_id,exc_info=True)
        try:await self._reconcile_departures()
        except Exception:LOGGER.warning('Could not reconcile poll eligibility',exc_info=True)

    async def _reconcile_departures(self):
        rows=self.engagement_repository.departure_candidates(self._departure_cursor)
        for row in rows:
            self._departure_cursor=(row['guild_id'],row['user_id'])
            guild=self.bot.get_guild(row['guild_id'])
            if guild is None:continue
            try:await guild.fetch_member(row['user_id'])
            except discord.NotFound:self.engagement_repository.remove_departed(row['guild_id'],row['user_id'])
            except discord.HTTPException:continue
        if not rows:self._departure_cursor=(0,0)

    @close_expired_polls.before_loop
    async def before_close_expired_polls(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_raw_member_remove(self,payload):
        self.engagement_repository.remove_departed(payload.guild_id,payload.user.id)

    @commands.Cog.listener()
    async def on_member_ban(self,guild,user):
        self.engagement_repository.remove_departed(guild.id,user.id)


async def setup(bot):
    await bot.add_cog(AdvancedPollsCog(bot))
