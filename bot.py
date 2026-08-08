"""Discord bot entry point."""
import asyncio
import logging

import discord
from discord.ext import commands

from config import Settings


class TuekaBot(commands.Bot):
    def __init__(self, settings: Settings) -> None:
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        intents.presences = True
        super().__init__(command_prefix="/", intents=intents)
        self.settings = settings

    async def setup_hook(self) -> None:
        for extension in self.settings.extensions:
            await self.load_extension(extension)
        synced = await self.tree.sync()
        logging.info("Synced %s application commands", len(synced))

    async def on_ready(self) -> None:
        logging.info("%s is online", self.user)


async def main() -> None:
    settings = Settings.from_env()
    logging.basicConfig(level=settings.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    bot = TuekaBot(settings)
    async with bot:
        await bot.start(settings.discord_token)


if __name__ == "__main__":
    asyncio.run(main())
