"""Suggestion delivery decisions using the shared leased outbox."""
from typing import Protocol
import asyncio

from discord_io import DiscordFailure, settle_external
from jobs import Outcome
from .models import normalize_settings


class SuggestionPort(Protocol):
    async def publish(self, item: dict, settings: dict, *, recover: bool) -> int: ...
    async def sync(self, item: dict, settings: dict) -> None: ...
    async def review_log(self, item: dict, settings: dict, key: int, *, recover: bool) -> None: ...
    async def discussion(self, item: dict, *, recover: bool) -> int: ...


class SuggestionDeliveryService:
    def __init__(self, repository, guild_settings, port: SuggestionPort):
        self.repository, self.guild_settings, self.port = repository, guild_settings, port

    _external = staticmethod(settle_external)

    def _presentation(self, suggestion_id: int):
        item = self.repository.delivery_suggestion(suggestion_id)
        if item is None:
            return None, None
        module = self.guild_settings.get_module(item['guild_id'], 'suggestions')
        if item.get('merged_into'):
            target=self.repository.get(item['guild_id'],item['merged_into'])
            if target:
                item={**item,'merged_target':{'channel_id':target['channel_id'],'message_id':target['message_id']}}
        return item, module

    def refresh_after_edit(self, item: dict, module_revision: int, *, job: dict | None = None) -> None:
        """A later-arriving edit must leave a reservation for the current card.

        Votes can change without a suggestion revision, and a canonical target
        can acquire its message ID independently, so compare the complete card.
        Failure to reserve propagates so an outbox edit remains retryable.
        """
        current, module = self._presentation(item['id'])
        if current is not None and (current != item or module['revision'] != module_revision):
            self.repository.queue_sync(item['guild_id'], item['id'], job=job)

    async def deliver(self, job: dict) -> Outcome:
        item, module = self._presentation(job['suggestion_id'])
        if item is None:
            return Outcome('Suggestion unavailable')
        settings = normalize_settings(module['settings'])
        recover = bool(job['delivery_started'] or job['payload'].get('recover'))
        external_started = settled = cancelled = False
        try:
            if not module['enabled']:
                return Outcome('Suggestions disabled', retry=True)
            if job['action'] == 'publish':
                if item.get('message_id'):
                    return Outcome()
                self.repository.delivery_state(job, started=True)
                presentation = {**item, 'status': 'pending'} if item['status'] == 'delivery_failed' else item
                external_started = True
                message_id = await self._external(self.port.publish(presentation, settings, recover=recover))
                self.repository.publication_delivered(job, message_id, discussion=bool(settings.get('discussion_enabled')))
            elif job['action'] == 'discussion':
                if not settings.get('discussion_enabled') or item.get('discussion_thread_id'):
                    return Outcome()
                if not item.get('message_id'):
                    return Outcome('Suggestion publication pending', retry=True)
                self.repository.delivery_state(job, started=True)
                external_started = True
                thread_id = await self._external(self.port.discussion(item, recover=recover))
                self.repository.discussion_delivered(job, thread_id)
            elif job['action'] == 'sync':
                if not item.get('message_id'):
                    return Outcome('Suggestion publication pending', retry=True)
                external_started = True
                await self._external(self.port.sync(item, settings))
                self.refresh_after_edit(item, module['revision'], job=job)
            elif job['action'] == 'review_log' and settings.get('log_channel_id'):
                self.repository.delivery_state(job, started=True)
                external_started = True
                await self._external(self.port.review_log({**item, **job['payload']}, settings, job['id'], recover=recover))
            settled = True
            return Outcome()
        except asyncio.CancelledError:
            cancelled = True
            raise
        except DiscordFailure as exc:
            if job['action'] in {'publish', 'review_log', 'discussion'}:
                uncertain = recover or exc.partial
                terminal = not (exc.retry or uncertain) or job['attempts'] >= 7
                self.repository.delivery_state(job, started=uncertain,
                    failed=str(exc) if job['action'] == 'publish' and terminal else None)
            elif external_started:
                self.repository.delivery_repair(item['guild_id'], item['id'], job)
            # The runner still owns this attempt and its bounded retry policy.
            # Receipt-only failures must not spawn unbounded replacement jobs.
            settled = True
            return Outcome(str(exc), retry=exc.retry or exc.partial or recover)
        finally:
            if external_started and not settled:
                self.repository.delivery_repair(item['guild_id'], item['id'], job, cancelled=cancelled)
