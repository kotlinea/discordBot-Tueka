"""One job at a time, with renewal and bounded repository-owned retries."""
import asyncio
import logging
from collections.abc import Awaitable, Callable
from contextlib import suppress

from .models import JobStore, LostLease, Outcome, RetryJob

LOGGER = logging.getLogger(__name__)


async def run_batch(store: JobStore, owner: str, handler: Callable[[dict], Awaitable[Outcome | None]], *, limit: int = 20, lease_seconds: int = 60) -> int:
    if limit < 1 or lease_seconds < 3:
        raise ValueError('Invalid runner limits')
    store.purge()
    count = 0
    for _ in range(limit):
        claim = store.claim(owner, lease_seconds=lease_seconds)
        if claim is None:
            break

        async def heartbeat():
            while True:
                await asyncio.sleep(lease_seconds / 3)
                if not store.renew(claim, lease_seconds=lease_seconds):
                    raise LostLease(f'Lease lost for job {claim.id}')

        task = asyncio.create_task(handler(claim.payload))
        renewal = asyncio.create_task(heartbeat())
        try:
            done, _ = await asyncio.wait((task, renewal), return_when=asyncio.FIRST_COMPLETED)
            if renewal in done:
                await renewal
            try:
                outcome = await task or Outcome()
            except RetryJob as exc:
                outcome = Outcome(str(exc) or type(exc).__name__, retry=True)
            except (PermissionError, ValueError) as exc:
                outcome = Outcome(str(exc) or type(exc).__name__)
            except Exception as exc:
                outcome = Outcome(str(exc) or type(exc).__name__, retry=True)
            if not store.finish(claim, outcome):
                raise LostLease(f'Lease lost before completion of job {claim.id}')
            count += 1
        except LostLease:
            LOGGER.warning('Job lease lost; cancelling handler job_id=%s', claim.id)
            break
        finally:
            task.cancel()
            renewal.cancel()
            for pending in (task, renewal):
                with suppress(asyncio.CancelledError, Exception):
                    await pending
    return count
