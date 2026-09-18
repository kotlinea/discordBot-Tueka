"""Graceful SIGTERM handling for foreground asyncio services, including PID 1."""
import asyncio
import signal

from database import close_pools


def run(factory) -> None:
    async def serve():
        loop = asyncio.get_running_loop()
        task = asyncio.current_task()
        stopping = False

        def stop(*_):
            nonlocal stopping
            if not stopping:
                stopping = True
                loop.call_soon_threadsafe(task.cancel)

        previous = signal.signal(signal.SIGTERM, stop)
        try:
            await factory()
        except asyncio.CancelledError:
            if not stopping:
                raise
        finally:
            signal.signal(signal.SIGTERM, previous)

    try:
        asyncio.run(serve())
    finally:
        close_pools()
