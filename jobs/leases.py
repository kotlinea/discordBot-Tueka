"""Renewable ownership around asynchronous resource lifecycle operations."""
import asyncio
from contextlib import suppress

from .repository import ResourceLeaseRepository


class ResourceLease(ResourceLeaseRepository):
    async def run(self, operation):
        self.acquire()

        async def heartbeat():
            while True:
                await asyncio.sleep(self.seconds / 3)
                self.renew()

        task = asyncio.create_task(operation(self))
        renewal = asyncio.create_task(heartbeat())
        try:
            done, _ = await asyncio.wait((task, renewal), return_when=asyncio.FIRST_COMPLETED)
            if renewal in done:
                await renewal
            result = await task
            self.check()
            return result
        finally:
            task.cancel()
            renewal.cancel()
            for pending in (task, renewal):
                with suppress(asyncio.CancelledError, Exception):
                    await pending
            self.release()
