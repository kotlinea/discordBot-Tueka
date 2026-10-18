"""Manager-only collection settings and bounded aggregate reports."""
import time
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Request
from dashboard.api import schemas
from dashboard.api.body import read_body, request_schema
from dashboard.api.dependencies import ApiDependencies
from dashboard.api.errors import api_error, revision_conflict
from dashboard.api.resources import GuildResources
from dashboard.api.route import ApiRoute, ERROR_RESPONSES
from insights.models import day_key, normalize


def wire(module):
    config = normalize(module['settings'])
    return {**module, 'settings': {**config, 'channel_ids': [str(c) for c in config['channel_ids']]}}


def create_router(context):
    router = APIRouter(route_class=ApiRoute, responses=ERROR_RESPONSES)
    auth = ApiDependencies(context.dashboard_repository, context.discord)
    repository = context.insights_repository

    @router.get('/guilds/{guild_id}/insights/settings', response_model=schemas.InsightsSettings)
    async def settings(request: Request, guild_id: int, _access=Depends(auth.read)):
        return wire(context.guild_settings_repository.get_module(guild_id, 'insights'))

    @router.put('/guilds/{guild_id}/insights/settings', response_model=schemas.InsightsSettings,
                dependencies=[Depends(auth.csrf)], openapi_extra=request_schema(schemas.InsightsSettingsInput))
    async def save(request: Request, guild_id: int, _access=Depends(auth.write)):
        body = await read_body(request, schemas.InsightsSettingsInput)
        try:
            config = normalize(body['settings'])
            if body['enabled']:
                resources = await GuildResources.fetch(context.discord, guild_id, live=True)
                for channel in config['channel_ids']:
                    item = resources.channels.get(channel)
                    if not item or int(item.get('type', -1)) not in (0, 2, 5, 13, 15, 16) or item.get('nsfw'):
                        raise ValueError('insights_channel')
            module = context.guild_settings_repository.set_module(guild_id, 'insights', enabled=body['enabled'],
                                                                 settings=config, expected_revision=body['revision'])
            return wire(module)
        except RuntimeError as exc:
            raise revision_conflict('設定が更新されています。再取得してから保存してください。') from exc
        except ValueError as exc:
            raise api_error(422, 'insights_invalid', '対象チャンネル・保存日数・収集条件を確認してください。') from exc

    @router.get('/guilds/{guild_id}/insights', response_model=schemas.InsightsReport)
    async def report(request: Request, guild_id: int, start: str | None = None, end: str | None = None, _access=Depends(auth.read)):
        try:
            config = normalize(context.guild_settings_repository.get_module(guild_id, 'insights')['settings'])
            today = date.fromisoformat(day_key(int(time.time())))
            first = (today - timedelta(days=min(7, config['retention_days']) - 1)).isoformat()
            return repository.report(guild_id, first if start is None else start, today.isoformat() if end is None else end)
        except ValueError as exc:
            raise api_error(422, 'insights_period', 'UTC日付で、保持期間内の最大90日を選択してください。') from exc

    return router
