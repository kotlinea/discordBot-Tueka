"""Compose acceptance fixture: real Cog startup, no Discord login/synchronization."""
import asyncio
from unittest.mock import AsyncMock, patch

from bot import TuekaBot
from config import Settings
from runtime.lifecycle import run


async def main():
    async with TuekaBot(Settings.from_env()) as bot:
        with patch.object(bot.tree, 'sync', AsyncMock(return_value=[])):
            await bot.setup_hook()
        print('Offline Bot extensions ready', flush=True)
        await asyncio.Event().wait()


if __name__ == '__main__':
    run(main)
