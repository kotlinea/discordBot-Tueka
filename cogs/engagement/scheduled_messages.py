"""Bounded schedule maintenance; Dashboard owns manager creation and changes."""
import logging
import os
import socket
from discord.ext import commands, tasks
from jobs import run_batch
from scheduling.repository import ScheduleRepository
from scheduling.delivery import ScheduleDeliveryService
from scheduling.discord_adapter import DiscordScheduleAdapter

LOGGER = logging.getLogger('tueka.scheduling')


class ScheduledMessagesCog(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.repository = ScheduleRepository(bot.settings.database_url)
        self.delivery = ScheduleDeliveryService(self.repository,DiscordScheduleAdapter(bot))
        self.owner = f'scheduling:{socket.gethostname()}:{os.getpid()}'

    async def cog_load(self):
        self.maintenance.start()

    def cog_unload(self):
        self.maintenance.cancel()

    @tasks.loop(seconds=10)
    async def maintenance(self):
        try:
            self.repository.purge_expired()
            self.repository.enqueue_due(limit=25)
            await run_batch(self.repository.jobs,self.owner,self.delivery.deliver,limit=5)
        except Exception as exc:
            LOGGER.error('Schedule maintenance failed type=%s',type(exc).__name__)

    @maintenance.before_loop
    async def before_maintenance(self):
        await self.bot.wait_until_ready()


async def setup(bot):
    await bot.add_cog(ScheduledMessagesCog(bot))
