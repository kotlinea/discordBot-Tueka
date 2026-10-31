"""Private paginated result browser; every page rechecks current disclosure."""
import discord
from engagement.polls.discord_adapter import embed_for
from engagement.polls.models import PollError


class ResultView(discord.ui.View):
    def __init__(self,cog,actor,poll_id):
        super().__init__(timeout=300)
        self.cog,self.actor,self.poll_id=cog,actor,poll_id
        self.section='options';self.page=0

    def render(self,result):
        if self.section not in ('options',) and self.section not in result:
            self.section='options';self.page=0
        self.clear_items()
        for section,label in (('options','選択肢・集計'),('participants','参加者'),('ballots','個別の投票')):
            if section!='options' and section not in result:continue
            button=discord.ui.Button(label=label,disabled=section==self.section)
            async def choose(i,s=section):self.section=s;self.page=0;await self.update(i)
            button.callback=choose;self.add_item(button)
        count=len(result['config']['options']) if self.section=='options' else len(result[self.section])
        size=5 if self.section=='options' else 10
        pages=max(1,(count+size-1)//size);self.page=min(self.page,pages-1)
        for delta,label in ((-1,'前のページ'),(1,'次のページ')):
            button=discord.ui.Button(label=label,disabled=not 0<=self.page+delta<pages)
            async def change(i,d=delta):self.page+=d;await self.update(i)
            button.callback=change;self.add_item(button)
        if self.section=='options':return embed_for(result,page=self.page)
        rows=result[self.section][self.page*size:(self.page+1)*size]
        if self.section=='participants':body='\n'.join(rows)
        else:body='\n'.join(f"{row['user_id']} → {', '.join(str(n+1) for n in row['choices'])}（重み {row['weight']}）" for row in rows)
        embed=discord.Embed(title='投票結果',description=body or '該当する投票はありません。')
        embed.set_footer(text=f'{self.page+1}/{pages}')
        return embed

    async def update(self,i):
        try:
            await i.response.defer()
            result=self.cog.service.read(await self.cog.actor(i),self.poll_id)
            await i.edit_original_response(embed=self.render(result),view=self)
        except PollError as exc:await self.cog.failure(i,exc)

    async def interaction_check(self,i):
        return i.user.id==self.actor.user_id and i.guild_id==self.actor.guild_id
