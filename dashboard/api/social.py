"""Social API routes."""
from __future__ import annotations
from .errors import api_error, revision_conflict, check_revision
from fastapi import Depends
import time
import importlib.util
from typing import Any
from fastapi import APIRouter, Header, Request
from dashboard.discord_api import ADMINISTRATOR, PERMISSION_BITS
from social.models import PROVIDERS, PROVIDER_EVENTS, TEMPLATE_VARIABLES, default_templates, normalize_account, render_template, validate_subscription
from .context import ApiContext
from .resources import GuildResources
from .dependencies import ApiDependencies

def create_router(context: ApiContext) -> APIRouter:
    router = APIRouter()
    auth = ApiDependencies(context.dashboard_repository, context.discord)
    discord = context.discord
    settings = context.settings
    social_repository = context.social_repository
    guild_settings_repository = context.guild_settings_repository
    manage = auth.manage

    def provider_available(provider: str) -> bool:
        if settings is None:
            return True
        return {'youtube': True, 'twitch': bool(settings.twitch_client_id and settings.twitch_client_secret and settings.dashboard_base_url and settings.social_webhook_secret), 'x': bool(settings.x_bearer_token), 'tiktok': importlib.util.find_spec('yt_dlp') is not None, 'instagram': bool(settings.instagram_rss_url_template)}[provider]

    def social_payload(subscription: dict[str, Any]) -> dict[str, Any]:
        target = social_repository.social_target(int(subscription['target_id'])) if subscription.get('target_id') else None
        public_target = {key: target.get(key) for key in ('id', 'provider', 'account_key', 'external_id', 'handle', 'display_name', 'avatar_url', 'status', 'last_error', 'last_checked_at', 'revision')} if target else None
        return {**subscription, 'id': int(subscription['id']), 'guild_id': str(subscription['guild_id']), 'channel_id': str(subscription['channel_id']), 'role_id': str(subscription['role_id']) if subscription.get('role_id') else None, 'event_channels': {key: str(value) for key, value in subscription.get('event_channels', {}).items()}, 'target': public_target}

    @router.get('/guilds/{guild_id}/social')
    async def social_summary(request: Request, guild_id: int, _access: str=Depends(auth.read)) -> dict[str, Any]:
        health = social_repository.social_worker_health()
        subscriptions = social_repository.social_subscriptions(guild_id)
        return {'providers': [{'id': provider, 'available': provider_available(provider), 'events': list(PROVIDER_EVENTS[provider]), 'count': sum((1 for item in subscriptions if item['provider'] == provider)), 'limit': int(getattr(settings, 'social_max_subscriptions_per_provider', 10))} for provider in PROVIDERS], 'worker': {**health, 'online': bool(health and int(health['heartbeat_at']) >= int(time.time()) - 30)} if health else {'online': False}}

    @router.get('/guilds/{guild_id}/social/{provider}/subscriptions')
    async def social_subscriptions(request: Request, guild_id: int, provider: str) -> dict[str, Any]:
        if provider not in PROVIDERS:
            raise api_error(404, 'provider_not_found', '通知サービスが見つかりません。')
        await manage(request, guild_id)
        return {'items': [social_payload(item) for item in social_repository.social_subscriptions(guild_id, provider)], 'available': provider_available(provider), 'events': list(PROVIDER_EVENTS[provider]), 'limit': int(getattr(settings, 'social_max_subscriptions_per_provider', 10)), 'variables': list(TEMPLATE_VARIABLES), 'defaults': default_templates(provider)}

    async def checked_social_body(request: Request, guild_id: int, provider: str, body: dict[str, Any] | None=None) -> dict[str, Any]:
        if provider not in PROVIDERS or not provider_available(provider):
            raise api_error(409, 'provider_unavailable', 'この通知サービスは運用設定が完了していません。')
        body = await request.json() if body is None else body
        value = validate_subscription(provider, body)
        snapshot = await GuildResources.fetch(discord, guild_id)
        permissions = snapshot.permissions
        text_channels = snapshot.channel_ids(0, 5)
        role_ids = snapshot.role_ids
        if value['channel_id'] not in text_channels or any((channel not in text_channels for channel in value['event_channels'].values())):
            raise ValueError('channel')
        if value['role_id'] is not None and value['role_id'] not in role_ids:
            raise ValueError('role')
        if not (permissions & ADMINISTRATOR or permissions & PERMISSION_BITS['send_messages']):
            raise PermissionError('send_messages')
        return value

    @router.post('/guilds/{guild_id}/social/{provider}/subscriptions', status_code=201, dependencies=[Depends(auth.csrf)])
    async def create_social_subscription(request: Request, guild_id: int, provider: str, _access: str=Depends(auth.write)) -> dict[str, Any]:
        try:
            value = await checked_social_body(request, guild_id, provider)
            saved = social_repository.save_social_subscription_v2(guild_id, provider, max_count=int(getattr(settings, 'social_max_subscriptions_per_provider', 10)), **value)
            guild_settings_repository.set_module(guild_id, f'{provider}_updates', enabled=any((bool(item['enabled']) for item in social_repository.social_subscriptions(guild_id, provider))))
            return social_payload(saved)
        except OverflowError as exc:
            raise api_error(422, 'social_limit', 'このサービスで登録できる上限に達しています。') from exc
        except (TypeError, ValueError, PermissionError) as exc:
            raise api_error(422, 'social_invalid', str(exc) or '対象アカウントと通知先を確認してください。') from exc

    @router.put('/guilds/{guild_id}/social/{provider}/subscriptions/{subscription_id}', dependencies=[Depends(auth.csrf)])
    async def update_social_subscription(request: Request, guild_id: int, provider: str, subscription_id: int, _access: str=Depends(auth.write)) -> dict[str, Any]:
        current = social_repository.social_subscription(subscription_id)
        if not current or int(current['guild_id']) != guild_id or current['provider'] != provider:
            raise api_error(404, 'subscription_not_found', '登録が見つかりません。')
        try:
            body = await request.json()
            value = await checked_social_body(request, guild_id, provider, body)
            if value['account_key'] != normalize_account(provider, str(current['account_id'])):
                raise ValueError('対象アカウントは変更できません。新しい登録を作成してください。')
            saved = social_repository.save_social_subscription_v2(guild_id, provider, subscription_id=subscription_id, expected_revision=int(body['revision']) if body.get('revision') is not None else None, **value)
            guild_settings_repository.set_module(guild_id, f'{provider}_updates', enabled=any((bool(item['enabled']) for item in social_repository.social_subscriptions(guild_id, provider))))
            return social_payload(saved)
        except RuntimeError as exc:
            raise revision_conflict('別の管理者がこの登録を更新しました。再読み込みしてください。') from exc
        except (TypeError, ValueError, PermissionError) as exc:
            raise api_error(422, 'social_invalid', str(exc) or '登録内容を確認してください。') from exc

    @router.delete('/guilds/{guild_id}/social/{provider}/subscriptions/{subscription_id}', status_code=204, dependencies=[Depends(auth.csrf)])
    async def delete_social_subscription(request: Request, guild_id: int, provider: str, subscription_id: int, if_match: str | None=Header(default=None), _access: str=Depends(auth.write)) -> None:
        current = social_repository.social_subscription(subscription_id)
        if not current or int(current['guild_id']) != guild_id or current['provider'] != provider:
            raise api_error(404, 'subscription_not_found', '登録が見つかりません。')
        check_revision(if_match, int(current.get('revision', 1)), '別の管理者がこの登録を更新しました。')
        social_repository.delete_social_subscription(guild_id, subscription_id)
        guild_settings_repository.set_module(guild_id, f'{provider}_updates', enabled=any((bool(item['enabled']) for item in social_repository.social_subscriptions(guild_id, provider))))

    @router.post('/guilds/{guild_id}/social/{provider}/subscriptions/{subscription_id}/retry', dependencies=[Depends(auth.csrf)])
    async def retry_social_subscription(request: Request, guild_id: int, provider: str, subscription_id: int, _access: str=Depends(auth.write)) -> dict[str, str]:
        current = social_repository.social_subscription(subscription_id)
        if not current or int(current['guild_id']) != guild_id or current['provider'] != provider or (not current.get('target_id')):
            raise api_error(404, 'subscription_not_found', '登録が見つかりません。')
        social_repository.request_social_target_retry(int(current['target_id']))
        return {'status': 'pending'}

    @router.post('/guilds/{guild_id}/social/{provider}/preview', dependencies=[Depends(auth.csrf)])
    async def preview_social_template(request: Request, guild_id: int, provider: str, _access: str=Depends(auth.read)) -> dict[str, Any]:
        try:
            body = await request.json()
            event = str(body.get('event') or PROVIDER_EVENTS[provider][0])
            template = validate_subscription(provider, {'account': 'preview', 'channel_id': 1, 'events': [event], 'templates': {event: body.get('template') or {}}})['templates'][event]
            sample = {'account': 'Sample Creator', 'handle': 'sample', 'title': '新しいコンテンツ', 'text': '通知本文のプレビューです。', 'url': 'https://example.com/content', 'platform': provider.title(), 'event': event, 'published_at': '2026-08-18 12:00', 'thumbnail': 'https://example.com/thumbnail.jpg', 'avatar': 'https://example.com/avatar.jpg', 'viewer_count': '123'}
            return {key: render_template(str(value), sample, limit={'content': 1900, 'title': 256, 'description': 4096, 'footer': 2048}.get(key, 500)) for key, value in template.items()}
        except (KeyError, TypeError, ValueError) as exc:
            raise api_error(422, 'template_invalid', str(exc) or '通知テンプレートを確認してください。') from exc
    return router
