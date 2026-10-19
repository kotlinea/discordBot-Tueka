"""Private Discord appeals and ModMail, including DM intake after removal."""
import logging
import os
import socket
import discord
from discord import app_commands
from discord.ext import commands, tasks
from jobs import run_batch
from appeals.repository import AppealRepository
from appeals.service import AppealService, parse_guild
from appeals.delivery import AppealDeliveryService
from appeals.discord_adapter import DiscordAppealAdapter
from applications.repository import ApplicationRepository
from moderation import ModerationRepository

LOGGER=logging.getLogger('tueka.appeals')


class PrivateMailModal(discord.ui.Modal):
    def __init__(self,cog,guild_id,*,case_id=None,application_id=None,item=None):
        super().__init__(title='異議申立て・ModMail',timeout=600)
        self.cog,self.guild_id,self.case_id,self.application_id,self.item=cog,guild_id,case_id,application_id,item
        self.content=discord.ui.TextInput(label='本文（秘密情報を入力しないでください）',style=discord.TextStyle.paragraph,min_length=1,max_length=2000)
        self.add_item(self.content)

    async def on_submit(self,interaction):
        await interaction.response.defer(ephemeral=True,thinking=True)
        try:
            if self.item:
                item=self.cog.repository.reply(self.guild_id,self.item['id'],interaction.user.id,self.content.value,revision=self.item['revision'],interaction=interaction.id)
            else:
                if self.case_id is None:
                    guild=self.cog.bot.get_guild(self.guild_id)
                    if not guild:raise PermissionError('guild_unavailable')
                    await guild.fetch_member(interaction.user.id)
                item=self.cog.service.open(self.guild_id,interaction.user.id,interaction.id,self.content.value,case_id=self.case_id,application_id=self.application_id)
            await interaction.followup.send(f"非公開のやり取り #{item['id']} を保存しました。/appeal-status で確認できます。",ephemeral=True)
        except (ValueError,PermissionError,LookupError,RuntimeError,discord.HTTPException):
            await interaction.followup.send('受付条件、本人のCase、受付状態、未解決のやり取りを確認してください。',ephemeral=True)

    async def on_error(self,interaction,error):
        LOGGER.error('Private conversation failed type=%s',type(error).__name__)
        if interaction.response.is_done():await interaction.followup.send('保存状況を /appeal-status で確認してください。',ephemeral=True)
        else:await interaction.response.send_message('保存状況を確認してください。',ephemeral=True)


class AppealsCog(commands.Cog):
    def __init__(self,bot):
        self.bot=bot
        url=bot.settings.database_url
        self.repository=AppealRepository(url)
        self.service=AppealService(self.repository,ModerationRepository(url),ApplicationRepository(url),None)
        self.delivery=AppealDeliveryService(self.repository,DiscordAppealAdapter(bot))
        self.owner=f'appeals:{socket.gethostname()}:{os.getpid()}'

    async def cog_load(self):self.maintenance.start()
    def cog_unload(self):self.maintenance.cancel()

    @tasks.loop(seconds=10)
    async def maintenance(self):
        try:
            self.repository.purge_expired()
            await run_batch(self.repository.jobs,self.owner,self.delivery.deliver,limit=5)
        except Exception as exc:LOGGER.error('Private conversation maintenance failed type=%s',type(exc).__name__)

    @maintenance.before_loop
    async def before_maintenance(self):await self.bot.wait_until_ready()

    @app_commands.command(name='appeal',description='自分のCaseに異議を申し立てます。DMでも利用できます。')
    @app_commands.describe(guild_id='対象サーバーID',case_id='自分のCase番号',application_id='関連する自分の申請番号（任意）')
    async def appeal(self,interaction:discord.Interaction,guild_id:str,case_id:int,application_id:int|None=None):
        try:
            guild=parse_guild(guild_id)
            case=self.service.moderation.case(guild,case_id)
            if not case or case['user_id'] != interaction.user.id:raise PermissionError()
            if not self.repository.settings.module_enabled(guild,'appeals'):raise PermissionError()
        except (ValueError,PermissionError):
            await interaction.response.send_message('受付中のサーバーと本人のCase番号を指定してください。',ephemeral=True);return
        await interaction.response.send_modal(PrivateMailModal(self,guild,case_id=case_id,application_id=application_id))

    @app_commands.command(name='modmail',description='管理者への非公開の問い合わせを作成します。')
    @app_commands.describe(guild_id='参加している対象サーバーID',application_id='関連する自分の申請番号（任意）')
    async def modmail(self,interaction:discord.Interaction,guild_id:str,application_id:int|None=None):
        try:
            guild=parse_guild(guild_id)
            if not self.repository.settings.module_enabled(guild,'appeals'):raise PermissionError()
        except (ValueError,PermissionError):
            await interaction.response.send_message('受付中のサーバーIDを指定してください。',ephemeral=True);return
        await interaction.response.send_modal(PrivateMailModal(self,guild,application_id=application_id))

    @app_commands.command(name='appeal-status',description='自分の異議申立て・ModMailと返信を確認します。')
    @app_commands.describe(guild_id='対象サーバーID',conversation_id='やり取り番号。空欄なら自分の一覧')
    async def status(self,interaction:discord.Interaction,guild_id:str,conversation_id:int|None=None):
        await interaction.response.defer(ephemeral=True,thinking=True)
        try:
            guild=parse_guild(guild_id)
            if conversation_id is None:
                items=self.repository.items(guild,author=interaction.user.id,limit=10)
                body='\n'.join(f"#{v['id']} {v['kind']} · {v['status']}" for v in items) or '保存期限内のやり取りはありません。'
            else:
                item=self.repository.item(guild,conversation_id,author=interaction.user.id)
                detail=self.repository.conversation(guild,conversation_id,author=interaction.user.id)
                body=f"#{item['id']} · {item['status']}\n"+'\n'.join(('管理者: ' if v['staff'] else '自分: ')+v['content'] for v in detail['messages'][-10:])
            await interaction.followup.send(body[-1900:],ephemeral=True,allowed_mentions=discord.AllowedMentions.none())
        except (ValueError,LookupError):await interaction.followup.send('本人の保存期限内のやり取りを指定してください。',ephemeral=True)

    @app_commands.command(name='appeal-reply',description='自分の未解決のやり取りに返信します。')
    @app_commands.describe(guild_id='対象サーバーID',conversation_id='自分のやり取り番号')
    async def reply(self,interaction:discord.Interaction,guild_id:str,conversation_id:int):
        try:
            guild=parse_guild(guild_id);item=self.repository.item(guild,conversation_id,author=interaction.user.id)
            if item['status'] not in ('open','reviewing'):raise ValueError()
        except (ValueError,LookupError):
            await interaction.response.send_message('本人の未解決のやり取りを指定してください。',ephemeral=True);return
        await interaction.response.send_modal(PrivateMailModal(self,guild,item=item))

    @app_commands.command(name='appeal-withdraw',description='自分の未解決のやり取りを取り下げます。')
    @app_commands.describe(guild_id='対象サーバーID',conversation_id='自分のやり取り番号')
    async def withdraw(self,interaction:discord.Interaction,guild_id:str,conversation_id:int):
        await interaction.response.defer(ephemeral=True,thinking=True)
        try:
            guild=parse_guild(guild_id);item=self.repository.item(guild,conversation_id,author=interaction.user.id)
            self.repository.transition(guild,conversation_id,interaction.user.id,'withdrawn','',revision=item['revision'],withdraw=True)
            await interaction.followup.send('取り下げました。',ephemeral=True)
        except (ValueError,LookupError,PermissionError,RuntimeError):await interaction.followup.send('状態が更新されたか受付が無効です。本人の状況を確認してください。',ephemeral=True)


async def setup(bot):await bot.add_cog(AppealsCog(bot))
