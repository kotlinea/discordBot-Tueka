"""Notification state transitions independent of Discord SDK objects."""
from discord_io import DiscordFailure
from guild_settings import GuildSettingsRepository

from .contracts import SocialMessagePort
from .models import default_templates, render_template
from .repository import SocialRepository

MODULE_FOR_PROVIDER = {name: f'{name}_updates' for name in ('youtube', 'twitch', 'tiktok', 'x', 'instagram')}


def notification(subscription: dict, event_type: str, payload: dict) -> tuple[str, dict]:
    template = (subscription.get('templates') or {}).get(event_type) or default_templates(subscription['provider'], [event_type])[event_type]
    def render(key, limit):
        return render_template(str(template.get(key, '')), payload, limit=limit)
    try:
        color = int(str(template.get('color', '#5865F2')).lstrip('#'), 16)
    except ValueError:
        color = 0x5865F2
    embed = {'color': color}
    for key, limit in (('title', 256), ('description', 4096), ('url', 500)):
        value = render(key, limit)
        if value:
            embed[key] = value
    for key in ('thumbnail', 'image'):
        url = render(key + '_url', 500)
        if url.startswith(('http://', 'https://')):
            embed[key] = {'url': url}
    footer = render('footer', 2048)
    if footer:
        embed['footer'] = {'text': footer}
    return render('content', 1900), embed


class SocialDeliveryService:
    def __init__(self, repository: SocialRepository, settings: GuildSettingsRepository, port: SocialMessagePort):
        self.repository, self.settings, self.port = repository, settings, port

    async def deliver(self, event: dict) -> bool:
        retry_needed = False
        event_type, event_key = str(event['event_type']), event['event_key']
        for subscription in self.repository.matching_social_subscriptions(event['provider'], event['account_id'], event_type):
            guild_id, subscription_id = subscription['guild_id'], subscription['id']
            if not self.settings.module_enabled(guild_id, MODULE_FOR_PROVIDER[event['provider']]):
                continue
            channel_id = int(subscription.get('event_channels', {}).get(event_type) or subscription['channel_id'])
            if not self.port.available(guild_id, channel_id):
                previous = self.repository.social_delivery(subscription_id, event_key)
                if self.repository.record_social_delivery(subscription_id, event_key, channel_id, None, 'pending'):
                    self.repository.fail_social_delivery(subscription_id, event_key, 'Discord channel is unavailable', retry=True,
                        uncertain=bool(previous and previous['state'] in {'pending', 'uncertain'}))
                    retry_needed = True
                continue
            text, embed = notification(subscription, event_type, event['payload'])
            if event_type == 'live_end':
                saved = self.repository.social_live_message(subscription_id, event['provider'], event['account_id'])
                if saved and self.port.available(guild_id, saved['discord_channel_id']):
                    try:
                        await self.port.edit(guild_id, saved['discord_channel_id'], saved['discord_message_id'], embed)
                        self.repository.record_social_delivery(subscription_id, event_key, saved['discord_channel_id'], saved['discord_message_id'], 'sent')
                        self.repository.update_social_delivery(subscription_id, event_key, saved['discord_message_id'])
                        self.repository.clear_social_live_message(subscription_id, event['provider'], event['account_id'])
                        continue
                    except DiscordFailure as exc:
                        if not exc.missing:
                            self.repository.record_social_delivery(subscription_id, event_key, saved['discord_channel_id'], saved['discord_message_id'], 'pending')
                            self.repository.fail_social_delivery(subscription_id, event_key, str(exc), retry=exc.retry)
                            retry_needed |= exc.retry
                            continue
            previous = self.repository.social_delivery(subscription_id, event_key)
            if previous and previous['state'] == 'sent' and event_type == 'live_start' and previous['discord_message_id']:
                self.repository.set_social_live_message(subscription_id, event['provider'], event['account_id'], previous['discord_channel_id'], previous['discord_message_id'])
            if not self.repository.record_social_delivery(subscription_id, event_key, channel_id, None, 'pending'):
                continue
            receipt = self.repository.social_delivery(subscription_id, event_key)
            try:
                message_id = await self.port.send(guild_id, channel_id, text, embed, subscription['role_id'],
                    f'{subscription_id}:{event_key}', recover=bool(previous and previous['state'] in {'pending', 'uncertain'}),
                    created_at=receipt['created_at'])
                # The intent remains pending if the DB fails after Discord succeeds.
                self.repository.update_social_delivery(subscription_id, event_key, message_id)
                if event_type == 'live_start':
                    self.repository.set_social_live_message(subscription_id, event['provider'], event['account_id'], channel_id, message_id)
            except DiscordFailure as exc:
                self.repository.fail_social_delivery(subscription_id, event_key, str(exc), retry=exc.retry, uncertain=exc.partial)
                retry_needed |= exc.retry or exc.partial
        return not retry_needed
