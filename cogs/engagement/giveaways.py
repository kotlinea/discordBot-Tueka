"""Persistent participation buttons and bounded campaign maintenance."""
import logging
import os
import socket
import discord
from discord.ext import commands, tasks
from giveaways.repository import GiveawayRepository
from giveaways.service import GiveawayService
from giveaways.discord_adapter import DiscordGiveawayAdapter
from jobs import run_batch

LOGGER = logging.getLogger('tueka.giveaways')


class GiveawaysCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.repo = GiveawayRepository(bot.settings.database_url)
        self.service = GiveawayService(self.repo, DiscordGiveawayAdapter(bot))
        self.owner = f'giveaways:{socket.gethostname()}:{os.getpid()}'

    async def cog_load(self):
        self.maintenance.start()

    def cog_unload(self):
        self.maintenance.cancel()

    @tasks.loop(seconds=5)
    async def maintenance(self):
        try:
            self.repo.purge_expired()
            await run_batch(self.repo.draw_jobs, self.owner + ':draw', self.service.draw, limit=5)
            await run_batch(self.repo.jobs, self.owner, self.service.publish, limit=10)
        except Exception as exc:
            LOGGER.error('Campaign maintenance failed type=%s', type(exc).__name__)

    @maintenance.before_loop
    async def ready(self):
        await self.bot.wait_until_ready()

    @commands.Cog.listener()
    async def on_interaction(self, interaction):
        if interaction.type != discord.InteractionType.component:
            return
        custom = (interaction.data or {}).get('custom_id', '')
        if not isinstance(custom, str) or not custom.startswith('tueka-campaign:'):
            return
        await interaction.response.defer(ephemeral=True)
        try:
            prefix, item, action = custom.split(':')
            if prefix != 'tueka-campaign' or not item.isascii() or not item.isdigit() or action not in ('join', 'leave'):
                raise ValueError('invalid_component')
            if not interaction.guild or not interaction.message or not isinstance(interaction.user, discord.Member):
                raise PermissionError('guild_member_required')
            changed = await self.service.participate(interaction.guild.id, int(item), interaction.user.id,
                                                     interaction.message.id, interaction.id, join=action == 'join')
            result = '参加を受け付けました。 / Entry saved.' if action == 'join' else '参加を取り消しました。 / Entry withdrawn.'
            if not changed:
                result = '参加状態は変更されていません。 / Entry unchanged.'
        except (ValueError, LookupError, PermissionError, RuntimeError):
            result = '受付状態・期限・参加条件を確認してください。 / Check availability, deadline and eligibility.'
        except Exception as exc:
            LOGGER.warning('Campaign interaction failed type=%s', type(exc).__name__)
            result = '参加状態を確認できませんでした。時間をおいて再試行してください。 / Please retry later.'
        await interaction.followup.send(result, ephemeral=True, allowed_mentions=discord.AllowedMentions.none())


async def setup(bot):
    await bot.add_cog(GiveawaysCog(bot))
