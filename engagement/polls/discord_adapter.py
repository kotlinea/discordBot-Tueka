"""Discord payloads and receipt reconciliation. Receives already-filtered results."""
import discord
from discord_io import DiscordFailure
from .models import disclose


def embed_for(result, *, page=0, marker=None):
    config = result['config']
    pages = max(1, (len(config['options']) + 4) // 5)
    page = max(0, min(page, pages-1))
    embed = discord.Embed(title='投票', description=config['question'] + ('\n\n'+config['description'] if config['description'] else ''), color=config['color'])
    lines, chunks = [], []
    for index in range(page*5, min(len(config['options']), page*5+5)):
        line = f"{index+1}. {config['emojis'][index]} {config['options'][index]}".replace('.  ', '. ')
        if 'counts' in result:
            line += f" — **{result['counts'][index]}**票"
            maximum=max(result['weighted_counts'],default=0)
            if maximum:
                line+=' '+'▰'*round(result['weighted_counts'][index]/maximum*10)
            if result['weighted_counts'][index] != result['counts'][index]:
                line += f"（重み {result['weighted_counts'][index]}）"
        if 'ranking' in result:
            line += f" · {result['ranking'][index]}位"
        if sum(len(item)+1 for item in lines)+len(line) > 1024:
            chunks.append('\n'.join(lines)); lines=[]
        lines.append(line)
    if lines:
        chunks.append('\n'.join(lines))
    for chunk in chunks:
        embed.add_field(name='選択肢', value=chunk, inline=False)
    if 'total' in result:
        embed.add_field(name='参加者数 / 選択件数', value=f"{result['total']} / {result['selections']}")
    footer = marker or f"{config['mode']} · {result['status']} · {page+1}/{pages} · 最大{config['max_choices']}択"
    embed.set_footer(text=footer)
    if config['image_url']:
        embed.set_image(url=config['image_url'])
    return embed


def public_view(message, config, *, revision, disabled=False):
    view = discord.ui.View(timeout=None)
    if config['ui'] == 'buttons':
        for index, option in enumerate(config['options']):
            view.add_item(discord.ui.Button(label=f'{index+1}. {option}'[:80], custom_id=f'tueka-poll:{message}:{index}:{revision}',
                                           style=getattr(discord.ButtonStyle,config['button_style']), disabled=disabled,emoji=config['emojis'][index] or None))
    else:
        view.add_item(discord.ui.Select(custom_id=f'tueka-poll-select:{message}:{revision}',placeholder='投票する選択肢',min_values=0,max_values=config['max_choices'],disabled=disabled,
            options=[discord.SelectOption(label=f'{i+1}. {option}'[:100],value=str(i),emoji=config['emojis'][i] or None) for i,option in enumerate(config['options'])]))
    view.add_item(discord.ui.Button(label='投票の変更・取消', custom_id=f'tueka-poll-vote:{message}:{revision}', disabled=disabled))
    view.add_item(discord.ui.Button(label='選択肢・結果を確認', custom_id=f'tueka-poll-details:{message}:0'))
    return view


class DiscordPollAdapter:
    def __init__(self, bot):
        self.bot = bot

    async def deliver(self, job, poll, *, recover):
        guild = self.bot.get_guild(job['guild_id'])
        if guild is None:
            raise DiscordFailure('poll_guild_unavailable', retry=True, partial=recover)
        try:
            channel_id = job['old_channel_id'] if job['action'] == 'stop_old' else job['channel_id']
            channel = await guild.fetch_channel(channel_id)
            if not isinstance(channel, (discord.TextChannel, discord.Thread)):
                raise DiscordFailure('poll_channel_invalid')
            if job['action'] == 'stop_old':
                try:
                    message = await channel.fetch_message(job['old_message_id'])
                    await message.edit(view=None)
                except discord.NotFound:
                    pass
                return job['old_message_id']
            marker = f"Tueka poll:{poll['id']}:job:{job['id']}"
            permissions = channel.permissions_for(guild.me)
            if job['action']=='archive':
                thread=await guild.fetch_channel(poll['thread_id'])
                if not isinstance(thread,discord.Thread) or thread.owner_id!=self.bot.user.id:
                    raise DiscordFailure('poll_thread_invalid')
                await thread.edit(archived=True)
                return thread.id
            if job['action']=='pin':
                message=await channel.fetch_message(poll['message_id'])
                await message.pin(reason='Tueka poll closed')
                return message.id
            if job['action']=='thread':
                if recover:
                    try:
                        thread=await guild.fetch_channel(poll['message_id'])
                    except discord.NotFound:
                        raise DiscordFailure('poll_thread_receipt_requires_reconciliation',partial=True) from None
                    if not isinstance(thread,discord.Thread) or thread.parent_id!=channel.id or thread.owner_id!=self.bot.user.id:
                        raise DiscordFailure('poll_thread_invalid',partial=True)
                    return thread.id
                message=await channel.fetch_message(poll['message_id'])
                thread=await message.create_thread(name=poll['question'][:100],reason='Tueka poll discussion')
                return thread.id
            if not permissions.view_channel or not permissions.read_message_history:
                raise DiscordFailure('poll_history_permission_required', partial=recover)
            if recover:
                async for message in channel.history(limit=200):
                    if message.author.id == self.bot.user.id and any(embed.footer.text == marker for embed in message.embeds):
                        return message.id
                raise DiscordFailure('poll_receipt_requires_reconciliation', partial=True)
            can_send=permissions.send_messages_in_threads if isinstance(channel,discord.Thread) else permissions.send_messages
            if not can_send or not permissions.embed_links:
                raise DiscordFailure('poll_send_permission_required')
            # Voting components are installed after receipt persistence and latest-state sync.
            result=disclose(poll)
            if job['action']=='announce':
                if 'counts' not in result:
                    raise DiscordFailure('poll_results_hidden')
                scores=result['weighted_counts']
                maximum=max(scores,default=0)
                winners=[str(index+1) for index,score in enumerate(scores) if score==maximum] if maximum else []
                announcement=discord.Embed(title='投票結果',description=('最多得票の選択肢: '+', '.join(winners)) if winners else '投票はありませんでした。',color=poll['config']['color'])
                announcement.set_footer(text=marker)
                message=await channel.send(embed=announcement,allowed_mentions=discord.AllowedMentions.none())
            else:
                message = await channel.send(embed=embed_for(result, marker=marker), allowed_mentions=discord.AllowedMentions.none())
            return message.id
        except discord.HTTPException as exc:
            raise DiscordFailure('poll_transport_error', retry=exc.status == 429 or exc.status >= 500,
                                 partial=recover or exc.status >= 500) from exc
