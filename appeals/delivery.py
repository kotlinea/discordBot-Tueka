"""Leased DM delivery, with receipt reconciliation after uncertain sends."""
from jobs import Outcome, LostLease
from discord_io import DiscordFailure


class DeliveryPaused(DiscordFailure):
    """Transport preparation finished, but no message send was attempted."""


class AppealDeliveryService:
    def __init__(self, repository, port):
        self.repository, self.port = repository, port

    async def deliver(self, job):
        if job['discord_message_id']:
            return Outcome()
        item=self.repository.delivery(job)
        if not item:
            self.repository.pause_delivery(job)
            raise LostLease('Appeal delivery paused before sending')
        recover=bool(job['delivery_started'])
        if not self.repository.delivery_state(job):
            raise LostLease('Appeal delivery lease lost')
        try:
            receipt=await self.port.notify(item,job['id'],recover=recover)
        except DeliveryPaused:
            self.repository.pause_delivery(job)
            raise LostLease('Appeal delivery paused before sending')
        except DiscordFailure as exc:
            if not recover and not exc.partial:
                if not self.repository.delivery_state(job,started=False):
                    raise LostLease('Appeal delivery lease lost')
            return Outcome('dm_delivery_uncertain' if recover or exc.partial else 'dm_delivery_failed',retry=exc.retry or exc.partial or recover)
        if not self.repository.delivery_state(job,receipt=receipt):
            raise LostLease('Appeal receipt lease lost')
        return Outcome()
