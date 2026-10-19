"""Wait for accepted I/O before propagating cancellation to its caller."""
import asyncio


async def settle_external(operation):
    task = asyncio.create_task(operation)
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError as cancellation:
        # Every parent cancellation must leave the accepted operation shielded.
        # A completed/cancelled child must not turn this into a busy wait.
        while not task.done():
            try:
                await asyncio.shield(task)
            except asyncio.CancelledError:
                continue
            except Exception:
                break
        try:
            task.result()
        finally:
            # Retrieve a child failure, but preserve the caller's cancellation.
            raise cancellation
