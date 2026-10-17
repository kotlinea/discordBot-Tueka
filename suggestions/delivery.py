"""Suggestion delivery decisions using the shared leased outbox."""
from typing import Protocol

from discord_io import DiscordFailure
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

    async def deliver(self, job: dict) -> Outcome:
        item = self.repository.delivery_suggestion(job['suggestion_id'])
        if item is None:
            return Outcome('Suggestion unavailable')
        module = self.guild_settings.get_module(item['guild_id'], 'suggestions')
        settings = normalize_settings(module['settings'])
        recover = bool(job['delivery_started'] or job['payload'].get('recover'))
        try:
            if not module['enabled']:
                raise DiscordFailure('Suggestions disabled')
            if job['action'] == 'publish':
                if item.get('message_id'):
                    return Outcome()
                self.repository.delivery_state(job, started=True)
                presentation = {**item, 'status': 'pending'} if item['status'] == 'delivery_failed' else item
                message_id = await self.port.publish(presentation, settings, recover=recover)
                self.repository.publication_delivered(job, message_id, discussion=bool(settings.get('discussion_enabled')))
            elif job['action'] == 'discussion':
                if not settings.get('discussion_enabled') or item.get('discussion_thread_id'):
                    return Outcome()
                if not item.get('message_id'):
                    return Outcome('Suggestion publication pending', retry=True)
                self.repository.delivery_state(job, started=True)
                thread_id = await self.port.discussion(item, recover=recover)
                self.repository.discussion_delivered(job, thread_id)
            elif job['action'] == 'sync':
                if not item.get('message_id'):
                    return Outcome('Suggestion publication pending', retry=True)
                await self.port.sync(item, settings)
            elif job['action'] == 'review_log' and settings.get('log_channel_id'):
                self.repository.delivery_state(job, started=True)
                await self.port.review_log({**item, **job['payload']}, settings, job['id'], recover=recover)
            return Outcome()
        except DiscordFailure as exc:
            if job['action'] in {'publish', 'review_log', 'discussion'}:
                uncertain = recover or exc.partial
                terminal = not (exc.retry or uncertain) or job['attempts'] >= 7
                self.repository.delivery_state(job, started=uncertain,
                    failed=str(exc) if job['action'] == 'publish' and terminal else None)
            return Outcome(str(exc), retry=exc.retry or exc.partial or recover)
