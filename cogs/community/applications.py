"""Private Discord form intake, own status and withdrawal; no channel publications."""
import logging
import time
import discord
from discord import app_commands
from discord.ext import commands, tasks
from applications.repository import ApplicationRepository
from applications.models import can_submit

LOGGER = logging.getLogger('tueka.applications')


class ApplicationModal(discord.ui.Modal):
    def __init__(self,cog,form):
        super().__init__(title=form['title'],timeout=600)
        self.cog,self.form = cog,form
        self.inputs = {}
        for field in form['fields']:
            control=discord.ui.TextInput(label=field['label'],custom_id=field['key'],
                style=discord.TextStyle.paragraph if field['style']=='paragraph' else discord.TextStyle.short,
                required=field['required'],min_length=field['min_length'] or None,max_length=field['max_length'])
            self.inputs[field['key']]=control
            self.add_item(control)

    async def on_submit(self,interaction):
        await interaction.response.defer(ephemeral=True,thinking=True)
        if not interaction.guild or interaction.guild.id != self.form['guild_id']:
            await interaction.followup.send('このサーバーのフォームではありません。',ephemeral=True)
            return
        try:
            # Check current membership/roles, not the Modal-opening snapshot.
            member=await interaction.guild.fetch_member(interaction.user.id)
            item=self.cog.repository.submit(interaction.guild.id,self.form['id'],member.id,interaction.id,
                {key:control.value for key,control in self.inputs.items()}, revision=self.form['revision'],
                roles=[r.id for r in member.roles], created_at=int(member.created_at.timestamp()),
                joined_at=int(member.joined_at.timestamp()) if member.joined_at else None)
        except (ValueError,LookupError,RuntimeError,PermissionError,discord.HTTPException):
            await interaction.followup.send('申請を受け付けられませんでした。受付条件・未審査の申請・フォームの更新を確認し、必要なら /apply から開き直してください。',ephemeral=True)
            return
        await interaction.followup.send(f"申請 #{item['id']} を受け付けました。/application-status で状況を確認できます。",ephemeral=True)

    async def on_error(self,interaction,error):
        # Never log answers, request bodies, or transport exception strings.
        LOGGER.error('Application modal failed guild=%s type=%s',self.form['guild_id'],type(error).__name__)
        message='受付状況を確認してください。保存できていなければ、フォームを開き直して再送信できます。'
        if interaction.response.is_done():
            await interaction.followup.send(message,ephemeral=True)
        else:
            await interaction.response.send_message(message,ephemeral=True)


class ApplicationsCog(commands.Cog):
    def __init__(self,bot):
        self.bot=bot
        self.repository=ApplicationRepository(bot.settings.database_url)

    async def cog_load(self):
        self.retention.start()

    def cog_unload(self):
        self.retention.cancel()

    @tasks.loop(minutes=1)
    async def retention(self):
        try:
            self.repository.purge_expired()
        except Exception as exc:
            LOGGER.error('Application retention failed type=%s',type(exc).__name__)

    @retention.before_loop
    async def before_retention(self):
        await self.bot.wait_until_ready()

    @app_commands.command(name='apply',description='応募・申請フォームに回答します。')
    @app_commands.guild_only()
    @app_commands.describe(form='回答するフォーム')
    async def apply(self,interaction:discord.Interaction,form:str):
        if not interaction.guild:
            return
        try:
            value=self.repository.form(interaction.guild.id,int(form))
            if not value['enabled'] or not self.repository.settings.module_enabled(interaction.guild.id,'applications'):
                raise PermissionError()
            member=interaction.user
            if not isinstance(member,discord.Member) or not can_submit(value,[r.id for r in member.roles],
                created_at=int(member.created_at.timestamp()),joined_at=int(member.joined_at.timestamp()) if member.joined_at else None,now=int(time.time())):
                raise PermissionError()
        except (ValueError,LookupError,PermissionError):
            await interaction.response.send_message('受付中で、ロール・日数条件を満たすフォームを選択してください。',ephemeral=True)
            return
        await interaction.response.send_modal(ApplicationModal(self,value))

    @apply.autocomplete('form')
    async def complete_form(self,interaction:discord.Interaction,current:str):
        if not interaction.guild or not self.repository.settings.module_enabled(interaction.guild.id,'applications'):
            return []
        return [app_commands.Choice(name=f"{f['title']} (#{f['id']})"[:100],value=str(f['id']))
                for f in self.repository.forms(interaction.guild.id) if f['enabled'] and current.lower() in f['title'].lower()][:25]

    @app_commands.command(name='application-status',description='自分の申請状況を確認し、必要なら未審査の申請を取り下げます。')
    @app_commands.guild_only()
    @app_commands.describe(withdraw_id='取り下げる申請番号。空欄なら状況確認だけを行います。')
    async def status(self,interaction:discord.Interaction,withdraw_id:int|None=None):
        if not interaction.guild:
            return
        await interaction.response.defer(ephemeral=True,thinking=True)
        if withdraw_id is not None:
            item=self.repository.item(interaction.guild.id,withdraw_id,author=interaction.user.id)
            if not item:
                await interaction.followup.send('取り下げられる申請が見つかりません。',ephemeral=True)
                return
            try:
                self.repository.transition(interaction.guild.id,item['id'],interaction.user.id,'withdrawn','',revision=item['revision'],withdraw=True)
            except (LookupError,RuntimeError,PermissionError):
                await interaction.followup.send('状態が更新されたか受付が無効です。申請状況を再確認してください。',ephemeral=True)
                return
            await interaction.followup.send('申請を取り下げました。',ephemeral=True)
            return
        items=self.repository.items(interaction.guild.id,author=interaction.user.id,limit=10)
        labels={'pending':'受付済み','reviewing':'審査中','approved':'承認','rejected':'却下','withdrawn':'取り下げ済み'}
        text='\n'.join(f"#{i['id']} {i['snapshot']['title']} — {labels[i['status']]}" for i in items) or '保存期限内の申請はありません。'
        await interaction.followup.send(text[:1900],ephemeral=True,allowed_mentions=discord.AllowedMentions.none())


async def setup(bot):
    await bot.add_cog(ApplicationsCog(bot))
