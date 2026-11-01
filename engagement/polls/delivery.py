"""Leased publication orchestration with persisted receipt reconciliation."""
from jobs import Outcome, LostLease
from discord_io import DiscordFailure


class PollDelivery:
    def __init__(self, repository, port):
        self.repository, self.port = repository, port

    async def deliver(self, job):
        state, poll = self.repository.start_delivery(job)
        if state == 'done':
            return Outcome()
        if state == 'paused':
            return Outcome('poll_disabled', retry=True)
        try:
            receipt = await self.port.deliver(job, poll, recover=state == 'recover')
        except DiscordFailure as exc:
            if state != 'recover' and not exc.partial:
                self.repository.reset_delivery(job)
            return Outcome('poll_delivery_uncertain' if state == 'recover' or exc.partial else 'poll_delivery_failed', retry=exc.retry or exc.partial or state == 'recover')
        if not self.repository.receipt(job, receipt):
            raise LostLease('Poll receipt lease lost')
        return Outcome()
