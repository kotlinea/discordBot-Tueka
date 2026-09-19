"""Discord bot entry point."""
import logging

import discord
from discord import app_commands
from discord.ext import commands

from config import Settings
from database import require_current
from runtime.lifecycle import run
from observability.heartbeat import ServiceHeartbeat
from observability.logging import configure_logging


class TuekaBot(commands.Bot):
    def __init__(self, settings: Settings) -> None:
        require_current(settings.database_url)
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        intents.presences = True
        super().__init__(command_prefix="/", intents=intents)
        self.settings = settings
        self.heartbeat = None

    async def setup_hook(self) -> None:
        self.tree.on_error = self.on_app_command_error
        for extension in self.settings.extensions:
            await self.load_extension(extension)
        synced = await self.tree.sync()
        logging.info("Synced %s application commands", len(synced))
        self.heartbeat = await ServiceHeartbeat('bot', self.settings.database_url, ready=self.is_ready).start()

    async def close(self) -> None:
        if self.heartbeat:
            await self.heartbeat.stop()
            self.heartbeat = None
        await super().close()

    async def on_ready(self) -> None:
        logging.info("%s is online", self.user)

    async def on_app_command_error(self, interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
        if isinstance(error, app_commands.MissingPermissions):
            message = "このコマンドを実行する権限がありません。"
        elif isinstance(error, app_commands.CheckFailure):
            message = "このコマンドはここでは実行できません。"
        else:
            logging.exception("Application command failed", exc_info=error)
            message = "コマンドの実行中にエラーが発生しました。"
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)


async def main() -> None:
    settings = Settings.from_env()
    configure_logging('bot', settings.log_level)
    bot = TuekaBot(settings)
    async with bot:
        await bot.start(settings.discord_token)


if __name__ == "__main__":
    run(main)
