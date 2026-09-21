"""Reaction roles API routes."""
from __future__ import annotations
from dashboard.api.errors import api_error, revision_conflict, check_revision
from fastapi import Depends
from database import IntegrityError
from typing import Any
from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import Response
from dashboard.discord_api import ADMINISTRATOR, PERMISSION_BITS
from reaction_roles import ReactionRoleRepository, ReactionRoleService, ReactionRoleValidationError
from features.defaults import RepositorySettingsAccess
from dashboard.api.context import ApiContext
from dashboard.api.route import ApiRoute, ERROR_RESPONSES
from dashboard.api import schemas
from dashboard.api.schemas import inputs
from dashboard.api.body import read_body, request_schema
from dashboard.api.resources import GuildResources
from dashboard.api.dependencies import ApiDependencies
REACTION_ROLE_PERMISSION_NAMES = {'manage_roles': 'ロールの管理', 'view_channel': 'チャンネルを見る', 'add_reactions': 'リアクションの追加', 'read_message_history': 'メッセージ履歴を読む', 'manage_messages': 'メッセージの管理', 'send_messages': 'メッセージを送信', 'embed_links': '埋め込みリンク'}

def create_settings(context: ApiContext) -> RepositorySettingsAccess:
    return RepositorySettingsAccess(context.reaction_role_repository)


def create_router(context: ApiContext) -> APIRouter:
    router = APIRouter(route_class=ApiRoute, responses=ERROR_RESPONSES)
    auth = ApiDependencies(context.dashboard_repository, context.discord)
    discord = context.discord
    reaction_role_repository = context.reaction_role_repository
    reaction_role_service = context.reaction_role_service
    manage = auth.manage

    def reaction_roles_available() -> tuple[ReactionRoleRepository, ReactionRoleService]:
        if not reaction_role_repository or not reaction_role_service:
            raise api_error(503, 'reaction_roles_unavailable', 'Reaction Rolesを初期化できません。')
        return (reaction_role_repository, reaction_role_service)

    def rr_payload(value: dict[str, Any]) -> dict[str, Any]:
        result = dict(value)
        for key in ('guild_id', 'channel_id', 'message_id', 'link_group_id'):
            if key in result:
                result[key] = str(result[key]) if result[key] is not None else None
        result['mappings'] = [{**item, 'role_id': str(item['role_id']), 'emoji_id': str(item['emoji_id']) if item.get('emoji_id') else None} for item in result.get('mappings', [])]
        result['whitelist_role_ids'] = [str(item) for item in result.get('whitelist_role_ids', [])]
        result['blacklist_role_ids'] = [str(item) for item in result.get('blacklist_role_ids', [])]
        return result

    async def checked_reaction_role(request: Request, guild_id: int, body: dict[str, Any]) -> tuple[dict[str, Any], int]:
        access = await manage(request, guild_id, live=True)
        user = await discord.current_user(access, use_cache=False)
        _, service = reaction_roles_available()
        value = service.validate(dict(body.get('message') or body))
        snapshot = await GuildResources.fetch(discord, guild_id)
        permissions = snapshot.permissions
        text_channels = {key: snapshot.channels[key] for key in snapshot.channel_ids(0)}
        role_ids = snapshot.role_ids
        emojis = {int(item['id']) for item in await discord.guild_emojis(guild_id, use_cache=False)}
        channel = text_channels.get(value['channel_id'])
        if channel is None:
            raise ReactionRoleValidationError('channel_invalid', 'このサーバーのテキストチャンネルを選択してください。', 'channel_id')
        for index, mapping in enumerate(value['mappings']):
            if mapping['role_id'] not in role_ids:
                raise ReactionRoleValidationError('role_invalid', 'Botが管理できるRoleを選択してください。', f'mappings.{index}.role_id')
            if mapping['emoji_id'] is not None and mapping['emoji_id'] not in emojis:
                raise ReactionRoleValidationError('emoji_invalid', 'このサーバーで利用できるEmojiを選択してください。', f'mappings.{index}.emoji')
        for key in ('whitelist_role_ids', 'blacklist_role_ids'):
            if any((role_id not in role_ids for role_id in value[key])):
                raise ReactionRoleValidationError('access_role_invalid', 'アクセスRoleを確認してください。', key)
        missing = []
        if not (permissions & ADMINISTRATOR or permissions & PERMISSION_BITS['manage_roles']):
            missing.append('manage_roles')
        channel_permissions = int(channel.get('bot_permissions', permissions))
        required = ['view_channel', 'add_reactions', 'read_message_history', 'manage_messages']
        if value['source'] == 'bot':
            required.extend(('send_messages', 'embed_links'))
        missing.extend((name for name in required if not channel_permissions & PERMISSION_BITS[name]))
        if missing:
            labels = [REACTION_ROLE_PERMISSION_NAMES[name] for name in dict.fromkeys(missing)]
            raise ReactionRoleValidationError('bot_permission_missing', 'Bot権限が不足しています: ' + '、'.join(labels), 'permissions')
        if value['source'] == 'external':
            message = await discord.channel_message(value['channel_id'], value['message_id'])
            if not message:
                raise ReactionRoleValidationError('message_not_found', '既存メッセージが見つかりません。', 'message_id')
        return (value, int(user['id']))

    def rr_error(exc: ReactionRoleValidationError) -> HTTPException:
        return api_error(422, exc.code, exc.message, errors=[{'path': exc.path, 'message': exc.message}])

    @router.get('/guilds/{guild_id}/reaction-roles', response_model=schemas.ReactionRoleOverview, response_model_exclude_unset=True)
    async def reaction_roles_overview(request: Request, guild_id: int, _access: str=Depends(auth.read)) -> dict[str, Any]:
        repository, _ = reaction_roles_available()
        items = repository.messages(guild_id)
        return {'settings': rr_payload(repository.settings(guild_id)), 'items': [rr_payload(item) for item in items], 'summary': {'active': sum((1 for item in items if item['enabled'] and item['status'] == 'active')), 'pending': sum((1 for item in items if item['status'] == 'pending')), 'failed': sum((1 for item in items if item['status'] == 'failed')), 'scheduled': sum((1 for item in items if item.get('self_destruct_at')))}, 'recoveries': [{**item, 'deleted_message_id': str(item['deleted_message_id'])} for item in repository.recoveries(guild_id)]}

    @router.put('/guilds/{guild_id}/reaction-roles/settings', dependencies=[Depends(auth.csrf)], response_model=schemas.ReactionRoleSettings, response_model_exclude_unset=True, openapi_extra=request_schema(inputs.ReactionRoleSettingsInput))
    async def save_reaction_role_settings(request: Request, guild_id: int, _access: str=Depends(auth.write)) -> dict[str, Any]:
        repository, _ = reaction_roles_available()
        body = await read_body(request, inputs.ReactionRoleSettingsInput)
        try:
            snapshot = await GuildResources.fetch(discord, guild_id)
            text_ids = snapshot.channel_ids(0)
            log_channel = int(body['log_channel_id']) if body.get('log_channel_id') else None
            if log_channel is not None and log_channel not in text_ids:
                raise ValueError('log_channel_id')
            saved = context.feature_settings['reaction_roles'].save(guild_id, enabled=bool(body.get('enabled')),
                settings={**body, 'log_channel_id': log_channel},
                expected_revision=int(body['revision']) if body.get('revision') is not None else None)['settings']
            return rr_payload(saved)
        except RuntimeError as exc:
            raise revision_conflict('別の管理者が設定を更新しました。') from exc
        except (TypeError, ValueError) as exc:
            raise api_error(422, 'settings_invalid', 'ログ先と通知設定を確認してください。') from exc

    @router.get('/guilds/{guild_id}/reaction-roles/events', response_model=schemas.Items[schemas.ReactionRoleEvent], response_model_exclude_unset=True)
    async def reaction_role_events(request: Request, guild_id: int, limit: int=100, _access: str=Depends(auth.read)) -> dict[str, Any]:
        repository, _ = reaction_roles_available()
        return {'items': repository.events(guild_id, limit)}

    @router.get('/guilds/{guild_id}/reaction-roles/link-groups', response_model=schemas.Items[schemas.ReactionRoleLinkGroup], response_model_exclude_unset=True)
    async def reaction_role_link_groups(request: Request, guild_id: int, _access: str=Depends(auth.read)) -> dict[str, Any]:
        repository, _ = reaction_roles_available()
        return {'items': repository.link_groups(guild_id)}

    @router.post('/guilds/{guild_id}/reaction-roles/link-groups', status_code=201, dependencies=[Depends(auth.csrf)], response_model=schemas.ReactionRoleLinkGroup, response_model_exclude_unset=True, openapi_extra=request_schema(inputs.LinkGroupInput))
    async def create_reaction_role_link_group(request: Request, guild_id: int, _access: str=Depends(auth.write)) -> dict[str, Any]:
        repository, _ = reaction_roles_available()
        body = await read_body(request, inputs.LinkGroupInput)
        try:
            return repository.create_link_group(guild_id, str(body.get('name') or 'Link Group'), [int(item) for item in body.get('message_ids', [])])
        except (TypeError, ValueError) as exc:
            raise api_error(422, 'link_invalid', '2件以上の互換性がある未Link設定を選択してください。') from exc

    @router.delete('/guilds/{guild_id}/reaction-roles/link-groups/{group_id}', status_code=204, dependencies=[Depends(auth.csrf)])
    async def delete_reaction_role_link_group(request: Request, guild_id: int, group_id: int, _access: str=Depends(auth.write)) -> Response:
        repository, _ = reaction_roles_available()
        repository.dissolve_link_group(guild_id, group_id)
        return Response(status_code=204)

    @router.post('/guilds/{guild_id}/reaction-roles/preview', dependencies=[Depends(auth.csrf)], response_model=schemas.PreviewResponse, response_model_exclude_unset=True, openapi_extra=request_schema(inputs.ReactionRoleInput))
    async def preview_reaction_role(request: Request, guild_id: int) -> dict[str, Any]:
        body = await read_body(request, inputs.ReactionRoleInput)
        repository, service = reaction_roles_available()
        try:
            value, _ = await checked_reaction_role(request, guild_id, body)
            result = service.preview(value)
            result['diagnostics'].append({'level': 'success', 'message': '対象チャンネルで必要なBot権限とRole階層を確認しました。'})
            guild_settings = repository.settings(guild_id)
            if int(guild_settings.get('revision', 0)) > 0 and (not guild_settings.get('enabled')):
                result['diagnostics'].append({'level': 'warning', 'message': 'Reaction Roles全体が無効です。有効化するまでRoleは付与されません。'})
            return result
        except ReactionRoleValidationError as exc:
            raise rr_error(exc) from exc

    @router.post('/guilds/{guild_id}/reaction-roles', status_code=201, dependencies=[Depends(auth.csrf)], response_model=schemas.ReactionRoleMessage, response_model_exclude_unset=True, openapi_extra=request_schema(inputs.ReactionRoleInput))
    async def create_reaction_role(request: Request, guild_id: int) -> dict[str, Any]:
        body = await read_body(request, inputs.ReactionRoleInput)
        repository, service = reaction_roles_available()
        try:
            value, actor_id = await checked_reaction_role(request, guild_id, body)
            return rr_payload(repository.create_message(guild_id, value, actor_id))
        except ReactionRoleValidationError as exc:
            raise rr_error(exc) from exc
        except IntegrityError as exc:
            raise api_error(409, 'message_exists', 'このDiscordメッセージはすでに登録されています。') from exc

    @router.get('/guilds/{guild_id}/reaction-roles/messages/{config_id}', response_model=schemas.ReactionRoleMessage, response_model_exclude_unset=True)
    async def reaction_role_detail(request: Request, guild_id: int, config_id: int, _access: str=Depends(auth.read)) -> dict[str, Any]:
        repository, _ = reaction_roles_available()
        value = repository.message(guild_id, config_id)
        if not value:
            raise api_error(404, 'reaction_role_not_found', 'Reaction Role設定が見つかりません。')
        return rr_payload(value)

    @router.put('/guilds/{guild_id}/reaction-roles/messages/{config_id}', dependencies=[Depends(auth.csrf)], response_model=schemas.ReactionRoleMessage, response_model_exclude_unset=True, openapi_extra=request_schema(inputs.ReactionRoleInput))
    async def update_reaction_role(request: Request, guild_id: int, config_id: int) -> dict[str, Any]:
        body = await read_body(request, inputs.ReactionRoleInput)
        repository, _ = reaction_roles_available()
        try:
            value, actor_id = await checked_reaction_role(request, guild_id, body)
            revision = int(body.get('revision', body.get('message', {}).get('revision', 0)))
            return rr_payload(repository.update_message(guild_id, config_id, value, revision, actor_id))
        except ReactionRoleValidationError as exc:
            raise rr_error(exc) from exc
        except RuntimeError as exc:
            raise revision_conflict('別の管理者が設定を更新しました。') from exc
        except KeyError as exc:
            raise api_error(404, 'reaction_role_not_found', 'Reaction Role設定が見つかりません。') from exc

    @router.delete('/guilds/{guild_id}/reaction-roles/messages/{config_id}', status_code=204, dependencies=[Depends(auth.csrf)])
    async def delete_reaction_role(request: Request, guild_id: int, config_id: int, if_match: str | None=Header(default=None), access: str=Depends(auth.write)) -> Response:
        repository, _ = reaction_roles_available()
        config = repository.message(guild_id, config_id)
        if not config:
            raise api_error(404, 'reaction_role_not_found', 'Reaction Role設定が見つかりません。')
        check_revision(if_match, int(config['revision']), '設定を再読み込みしてください。', required=True)
        actor = await discord.current_user(access, use_cache=False)
        try:
            repository.delete_message(guild_id, config_id, recoverable=False, actor_id=int(actor['id']), expected_revision=config['revision'], queue_delete=True)
        except RuntimeError as exc:
            raise revision_conflict('設定を再読み込みしてください。') from exc
        return Response(status_code=204)

    @router.post('/guilds/{guild_id}/reaction-roles/messages/{config_id}/fix', status_code=202, dependencies=[Depends(auth.csrf)], response_model=schemas.StatusResponse, response_model_exclude_unset=True)
    async def fix_reaction_role(request: Request, guild_id: int, config_id: int, _access: str=Depends(auth.write)) -> dict[str, Any]:
        repository, _ = reaction_roles_available()
        if not repository.message(guild_id, config_id):
            raise api_error(404, 'reaction_role_not_found', 'Reaction Role設定が見つかりません。')
        repository.queue_action(guild_id, config_id, 'fix', {})
        return {'status': 'queued'}

    @router.post('/guilds/{guild_id}/reaction-roles/messages/{config_id}/move', status_code=202, dependencies=[Depends(auth.csrf)], response_model=schemas.StatusResponse, response_model_exclude_unset=True, openapi_extra=request_schema(inputs.MoveInput))
    async def move_reaction_role(request: Request, guild_id: int, config_id: int, _access: str=Depends(auth.write)) -> dict[str, Any]:
        repository, _ = reaction_roles_available()
        body = await read_body(request, inputs.MoveInput)
        config = repository.message(guild_id, config_id)
        if not config:
            raise api_error(404, 'reaction_role_not_found', 'Reaction Role設定が見つかりません。')
        snapshot = await GuildResources.fetch(discord, guild_id)
        channel_id = int(body.get('channel_id', 0))
        message_id = int(body.get('message_id', 0))
        if channel_id not in snapshot.channel_ids(0) or not await discord.channel_message(channel_id, message_id):
            raise api_error(422, 'move_invalid', '移動先メッセージを確認してください。')
        repository.queue_action(guild_id, config_id, 'move', {'channel_id': channel_id, 'message_id': message_id, 'revision': config['revision']})
        return {'status': 'queued'}

    @router.post('/guilds/{guild_id}/reaction-roles/recoveries/{deleted_message_id}/restore', status_code=201, dependencies=[Depends(auth.csrf)], response_model=schemas.ReactionRoleMessage, response_model_exclude_unset=True, openapi_extra=request_schema(inputs.MoveInput))
    async def restore_reaction_role(request: Request, guild_id: int, deleted_message_id: int, _access: str=Depends(auth.write)) -> dict[str, Any]:
        repository, _ = reaction_roles_available()
        snapshot = repository.recovery(guild_id, deleted_message_id)
        if not snapshot:
            raise api_error(404, 'recovery_not_found', '復旧データが見つかりません。')
        body = await read_body(request, inputs.MoveInput)
        snapshot.update({'source': 'external', 'channel_id': body.get('channel_id'), 'message_id': body.get('message_id'), 'self_destruct_at': None, 'link_group_id': None})
        try:
            value, actor_id = await checked_reaction_role(request, guild_id, {'message': snapshot})
            created = repository.create_message(guild_id, value, actor_id)
            repository.consume_recovery(guild_id, deleted_message_id)
            return rr_payload(created)
        except ReactionRoleValidationError as exc:
            raise rr_error(exc) from exc
    return router
