"""Leased delivery with a durable send boundary and no blind resends."""
from jobs import Outcome, LostLease
from discord_io import DiscordFailure


class ScheduleDeliveryService:
    def __init__(self, repository, port):
        self.repository, self.port = repository, port

    async def deliver(self, job):
        try:
            state = self.repository.start_delivery(job)
        except PermissionError:
            return Outcome('schedule_disabled_or_cancelled', retry=True)
        except LookupError:
            return Outcome('schedule_expired')
        if state == 'done':
            return Outcome()
        if state == 'missed':
            return Outcome('schedule_deadline_passed')
        recover = state == 'recover'
        try:
            receipt = await self.port.deliver(job, recover=recover)
        except DiscordFailure as exc:
            if not recover and not exc.partial:
                if not self.repository.delivery_state(job, started=False):
                    raise LostLease('Scheduled delivery lease lost')
            return Outcome('schedule_delivery_uncertain' if recover or exc.partial else 'schedule_delivery_failed', retry=recover or exc.partial or exc.retry)
        if not self.repository.delivery_state(job, receipt=receipt):
            raise LostLease('Scheduled receipt lease lost')
        return Outcome()
