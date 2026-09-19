"""Compose acceptance fixture: real Cog startup, no Discord login/synchronization."""
import asyncio
from unittest.mock import AsyncMock, patch

from bot import TuekaBot
from config import Settings
from runtime.lifecycle import run
from observability.logging import configure_logging


async def main():
    configure_logging('bot')
    async with TuekaBot(Settings.from_env()) as bot:
        # Gateway readiness is simulated only in this isolated acceptance fixture.
        with patch.object(bot.tree, 'sync', AsyncMock(return_value=[])), patch.object(bot, 'is_ready', return_value=True):
            await bot.setup_hook()
            print('Offline Bot extensions ready', flush=True)
            await asyncio.Event().wait()


if __name__ == '__main__':
    run(main)
