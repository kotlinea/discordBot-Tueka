"""Author-only poll builder drafts and edit preview; publication is explicit."""
import discord
from copy import deepcopy
from engagement.polls.models import normalize, PollError, disclose
from engagement.polls.discord_adapter import embed_for


class BuilderView(discord.ui.View):
    def __init__(self, cog, actor, poll, *, editing=False):
        super().__init__(timeout=900)
        self.cog,self.actor,self.poll,self.editing=cog,actor,poll,editing
        self.values=deepcopy(poll['config'])
        self.selected=0
        self.page=0
        self.message=None
        self.rebuild()

    async def interaction_check(self, interaction):
        return interaction.user.id==self.actor.user_id and interaction.guild_id==self.actor.guild_id

    def preview(self):
        return embed_for(disclose({**self.poll,'config':normalize(self.values)}),page=self.page)

    async def update(self, interaction):
        self.rebuild()
        await interaction.response.edit_message(embed=self.preview(),view=self)

    def rebuild(self):
        self.clear_items()
        choice=discord.ui.Select(placeholder='編集する選択肢',options=[discord.SelectOption(label=f'{i+1}. {text}'[:100],value=str(i),default=i==self.selected) for i,text in enumerate(self.values['options'])])
        async def select(i):
            self.selected=int(choice.values[0]);self.page=self.selected//5
            await self.update(i)
        choice.callback=select;self.add_item(choice)
        self.button('質問・説明',self.question)
        self.button('選択肢を編集',self.option)
        self.button('選択肢を追加',self.add,disabled=len(self.values['options'])>=25)
        self.button('選択肢を削除',self.remove,disabled=len(self.values['options'])<=2)
        self.button('投票方式・表示',self.settings)
        self.button('公開範囲',self.visibility)
        self.button('ボタン色: '+self.values['button_style'],self.style,style=getattr(discord.ButtonStyle,self.values['button_style']))
        roles=discord.ui.RoleSelect(placeholder='投票を許可するロール（空なら全員）',min_values=0,max_values=25,
            default_values=[discord.SelectDefaultValue(id=int(role),type=discord.SelectDefaultValueType.role) for role in self.values['allowed_roles'][:25]])
        async def allow(i):
            self.values['allowed_roles']=[str(role.id) for role in roles.values]
            await self.update(i)
        roles.callback=allow;self.add_item(roles)
        self.button('保存' if self.editing else 'Create：公開する',self.save,style=discord.ButtonStyle.primary)
        self.button('破棄',self.discard)

    def button(self,label,callback,*,disabled=False,style=discord.ButtonStyle.secondary):
        button=discord.ui.Button(label=label,style=style,disabled=disabled)
        button.callback=callback;self.add_item(button)

    async def modal(self, interaction, title, fields, apply):
        view=self
        class Editor(discord.ui.Modal,title=title):
            async def on_submit(self,i):
                previous=deepcopy(view.values)
                try:
                    apply([str(field.value) for field in self.children])
                    normalize(view.values)
                    await view.update(i)
                except (PollError,ValueError):
                    view.values=previous
                    await view.cog.failure(i,PollError('invalid'))
        modal=Editor()
        for label,value,maximum,required in fields:
            modal.add_item(discord.ui.TextInput(label=label,default=value,max_length=maximum,required=required,style=discord.TextStyle.paragraph if maximum>256 else discord.TextStyle.short))
        await interaction.response.send_modal(modal)

    async def question(self,i):
        def apply(values):self.values.update(question=values[0],description=values[1])
        await self.modal(i,'質問・説明',[('質問',self.values['question'],1024,True),('説明',self.values['description'],2000,False)],apply)

    async def option(self,i):
        index=self.selected
        def apply(values):self.values['options'][index]=values[0];self.values['emojis'][index]=values[1]
        await self.modal(i,'選択肢',[('選択肢',self.values['options'][index],256,True),('絵文字',self.values['emojis'][index],100,False)],apply)

    async def add(self,i):
        number=len(self.values['options'])+1
        self.values['options']=[*self.values['options'],f'選択肢 {number}']
        self.values['emojis']=[*self.values['emojis'],''];self.selected=number-1
        await self.update(i)

    async def remove(self,i):
        self.values['options']=[text for n,text in enumerate(self.values['options']) if n!=self.selected]
        self.values['emojis']=[text for n,text in enumerate(self.values['emojis']) if n!=self.selected]
        self.selected=0
        self.values['max_choices']=min(self.values['max_choices'],len(self.values['options']))
        await self.update(i)

    async def settings(self,i):
        def apply(values):
            self.values.update(max_choices=int(values[0]),mode=values[1],ui=values[2],image_url=values[3] or None,color=int(values[4].lstrip('#'),16))
        await self.modal(i,'投票方式・表示',[('最大選択数',str(self.values['max_choices']),2,True),('方式名（初期値 anonymous）',self.values['mode'],20,True),('操作: buttons/select',self.values['ui'],10,True),('画像URL',self.values['image_url'] or '',2048,False),('色（16進数）',f"{self.values['color']:06x}",7,True)],apply)

    async def visibility(self,i):
        fields=('counts','ranking','total','participants','ballots')
        def apply(values):
            self.values['mode']='custom'
            self.values['visibility']={stage:dict(zip(fields,[x.strip() for x in raw.split(',')])) for stage,raw in zip(('open','closed'),values)}
        await self.modal(i,'公開範囲：票数,順位,総数,参加者,個票',[('投票中: everyone/admins/hidden',','.join(self.values['visibility']['open'][key] for key in fields),100,True),('終了後: everyone/admins/hidden',','.join(self.values['visibility']['closed'][key] for key in fields),100,True)],apply)

    async def style(self,i):
        styles=('primary','secondary','success','danger')
        self.values['button_style']=styles[(styles.index(self.values['button_style'])+1)%4]
        await self.update(i)

    async def save(self,i):
        try:
            actor=await self.cog.actor(i)
            self.cog.validate_config(i,normalize(self.values))
            poll=self.cog.service.edit(actor,self.poll['id'],self.values,self.poll['revision'],closes_at=self.poll['closes_at'])
            if not self.editing:self.cog.engagement_repository.launch(actor.guild_id,poll['id'],actor.user_id,poll['revision'],principal=actor)
            await i.response.edit_message(content='保存しました。' if self.editing else f"投票 #{poll['id']} の公開を受け付けました。",embed=None,view=None)
            self.stop()
        except PollError as exc:await self.cog.failure(i,exc)

    async def discard(self,i):
        if not self.editing:
            try:self.cog.service.transition(await self.cog.actor(i),self.poll['id'],'cancel',self.poll['revision'])
            except PollError as exc:await self.cog.failure(i,exc);return
        await i.response.edit_message(content='破棄しました。',embed=None,view=None);self.stop()
