"""Moderation API routes."""
from __future__ import annotations
from dashboard.api.errors import api_error, revision_conflict, check_revision
from fastapi import Depends
import secrets
from typing import Any
from fastapi import APIRouter, Header, Request
from moderation import AutoModEngine, MessageContext, default_rule, validate_rule
from dashboard.discord_api import ADMINISTRATOR, PERMISSION_BITS
from dashboard.api.context import ApiContext
from dashboard.api.route import ApiRoute, ERROR_RESPONSES
from dashboard.api import schemas
from dashboard.api.schemas import inputs
from dashboard.api.body import read_body, request_schema
from dashboard.api.dependencies import ApiDependencies
from dashboard.api.serialization import _serialize_rule_resource_ids
from moderation.rules import FAMILY_TRIGGERS, rule_template
ALLOWED_ACTIONS = {'warn', 'timeout', 'untimeout', 'kick', 'ban', 'unban', 'softban', 'purge', 'lock', 'unlock', 'lockdown', 'unlockdown'}

def create_router(context: ApiContext) -> APIRouter:
    router = APIRouter(route_class=ApiRoute, responses=ERROR_RESPONSES)
    auth = ApiDependencies(context.dashboard_repository, context.discord)
    discord = context.discord
    moderation_repository = context.moderation_repository
    guild_settings_repository = context.guild_settings_repository
    manage = auth.manage

    @router.get('/guilds/{guild_id}/moderation/{family}/templates/{trigger_type}', response_model=schemas.Rule, response_model_exclude_unset=True)
    async def template(request: Request, guild_id: int, family: str, trigger_type: str, _access: str=Depends(auth.read)) -> dict[str, Any]:
        try:
            return _serialize_rule_resource_ids(rule_template(family, trigger_type))
        except ValueError as exc:
            raise api_error(404, 'template_not_found', 'ルールの初期設定が見つかりません。') from exc

    @router.get('/guilds/{guild_id}/moderation/{family}/rules', response_model=schemas.RulesResponse, response_model_exclude_unset=True)
    async def rules(request: Request, guild_id: int, family: str) -> dict[str, Any]:
        if family not in FAMILY_TRIGGERS:
            raise api_error(404, 'family_not_found', 'ルール種別が見つかりません。')
        await manage(request, guild_id)
        return {'items': [_serialize_rule_resource_ids(item) for item in moderation_repository.moderation_rules(guild_id, family=family)], 'trigger_types': FAMILY_TRIGGERS[family]}

    @router.get('/guilds/{guild_id}/moderation/{family}/rules/{rule_id}', response_model=schemas.Rule, response_model_exclude_unset=True)
    async def rule(request: Request, guild_id: int, family: str, rule_id: int, _access: str=Depends(auth.read)) -> dict[str, Any]:
        value = moderation_repository.moderation_rule(guild_id, rule_id)
        if not value or value['family'] != family:
            raise api_error(404, 'rule_not_found', 'ルールが見つかりません。')
        return _serialize_rule_resource_ids(value)

    def normalized_rule(body: dict[str, Any], family: str) -> dict[str, Any]:
        trigger = str(body.get('trigger_type', ''))
        if family not in FAMILY_TRIGGERS or trigger not in FAMILY_TRIGGERS[family]:
            raise ValueError('trigger_type')
        defaults = default_rule(trigger)
        value = {**defaults, **body, 'family': family, 'trigger_config': {**defaults['trigger_config'], **dict(body.get('trigger_config') or {})}}
        value['event_type'] = str(body.get('event_type') or ('member_join' if trigger in {'join_rate', 'new_account_ratio'} else 'member_remove' if trigger == 'leave_rate' else 'reaction_add' if trigger.startswith('reaction_') else 'message_create'))
        return validate_rule(value)

    @router.post('/guilds/{guild_id}/moderation/{family}/rules', status_code=201, dependencies=[Depends(auth.csrf)], response_model=schemas.Rule, response_model_exclude_unset=True, openapi_extra=request_schema(inputs.RuleInput))
    async def create_rule(request: Request, guild_id: int, family: str, _access: str=Depends(auth.write)) -> dict[str, Any]:
        try:
            value = normalized_rule(await read_body(request, inputs.RuleInput), family)
            value['priority'] = moderation_repository.next_moderation_rule_priority(guild_id, family)
            return _serialize_rule_resource_ids(moderation_repository.save_moderation_rule(guild_id, value))
        except RuntimeError as exc:
            raise revision_conflict('別の管理者がルールを更新しました。再読み込みしてください。') from exc
        except (TypeError, ValueError) as exc:
            raise api_error(422, 'rule_invalid', str(exc) or 'ルールを確認してください。') from exc

    @router.put('/guilds/{guild_id}/moderation/{family}/rules/order', dependencies=[Depends(auth.csrf)], response_model=schemas.Items[schemas.Rule], response_model_exclude_unset=True, openapi_extra=request_schema(inputs.ReorderInput))
    async def reorder_rules(request: Request, guild_id: int, family: str, _access: str=Depends(auth.write)) -> dict[str, Any]:
        if family not in FAMILY_TRIGGERS:
            raise api_error(404, 'family_not_found', 'ルール種別が見つかりません。')
        try:
            body = await read_body(request, inputs.ReorderInput)
            items = body.get('items')
            if not isinstance(items, list):
                raise ValueError('items')
            return {'items': [_serialize_rule_resource_ids(item) for item in moderation_repository.reorder_moderation_rules(guild_id, family, items)]}
        except RuntimeError as exc:
            raise revision_conflict('別の管理者がルール一覧を更新しました。再読み込みしてください。') from exc
        except (TypeError, ValueError) as exc:
            raise api_error(422, 'rule_order_invalid', 'ルールの順序を再読み込みして、もう一度保存してください。') from exc

    @router.put('/guilds/{guild_id}/moderation/{family}/rules/state', dependencies=[Depends(auth.csrf)], response_model=schemas.Items[schemas.Rule], response_model_exclude_unset=True, openapi_extra=request_schema(inputs.RuleStateInput))
    async def set_rules_state(request: Request, guild_id: int, family: str, _access: str=Depends(auth.write)) -> dict[str, Any]:
        if family not in FAMILY_TRIGGERS:
            raise api_error(404, 'family_not_found', 'ルール種別が見つかりません。')
        body = await read_body(request, inputs.RuleStateInput)
        try:
            items = moderation_repository.set_moderation_rules_enabled(guild_id, family, body['items'], body['enabled'])
            return {'items': [_serialize_rule_resource_ids(item) for item in items]}
        except RuntimeError as exc:
            raise revision_conflict('別の管理者がルールを更新しました。一覧を再読み込みして選択を確認してください。') from exc
        except (TypeError, ValueError) as exc:
            raise api_error(422, 'rule_state_invalid', str(exc)) from exc

    @router.put('/guilds/{guild_id}/moderation/{family}/rules/{rule_id}', dependencies=[Depends(auth.csrf)], response_model=schemas.Rule, response_model_exclude_unset=True, openapi_extra=request_schema(inputs.RuleInput))
    async def update_rule(request: Request, guild_id: int, family: str, rule_id: int, _access: str=Depends(auth.write)) -> dict[str, Any]:
        body, current = (await read_body(request, inputs.RuleInput), moderation_repository.moderation_rule(guild_id, rule_id))
        if not current or current['family'] != family:
            raise api_error(404, 'rule_not_found', 'ルールが見つかりません。')
        check_revision(body.get('revision'), int(current['revision']), '別の管理者がルールを更新しました。再読み込みしてください。')
        try:
            value = normalized_rule(body, family)
            value['priority'] = current['priority']
            return _serialize_rule_resource_ids(moderation_repository.save_moderation_rule(guild_id, value, rule_id, expected_revision=current['revision']))
        except RuntimeError as exc:
            raise revision_conflict('別の管理者がルールを更新しました。再読み込みしてください。') from exc
        except (TypeError, ValueError) as exc:
            raise api_error(422, 'rule_invalid', str(exc) or 'ルールを確認してください。') from exc

    @router.delete('/guilds/{guild_id}/moderation/{family}/rules/{rule_id}', status_code=204, dependencies=[Depends(auth.csrf)])
    async def delete_rule(request: Request, guild_id: int, family: str, rule_id: int, if_match: str | None=Header(default=None), _access: str=Depends(auth.write)) -> None:
        current = moderation_repository.moderation_rule(guild_id, rule_id)
        if not current or current['family'] != family:
            raise api_error(404, 'rule_not_found', 'ルールが見つかりません。')
        check_revision(if_match, int(current['revision']), '別の管理者がルールを更新しました。')
        try:
            moderation_repository.delete_moderation_rule(guild_id, rule_id, expected_revision=current['revision'])
        except RuntimeError as exc:
            raise revision_conflict('別の管理者がルールを更新しました。') from exc

    @router.post('/guilds/{guild_id}/moderation/{family}/rules/{rule_id}/duplicate', status_code=201, dependencies=[Depends(auth.csrf)], response_model=schemas.Rule, response_model_exclude_unset=True)
    async def duplicate_rule(request: Request, guild_id: int, family: str, rule_id: int, _access: str=Depends(auth.write)) -> dict[str, Any]:
        current = moderation_repository.moderation_rule(guild_id, rule_id)
        if not current or current['family'] != family:
            raise api_error(404, 'rule_not_found', 'ルールが見つかりません。')
        copy = {key: value for key, value in current.items() if key not in {'id', 'guild_id', 'revision', 'created_at', 'updated_at'}}
        copy.update({'name': f"{current['name']} (コピー)"[:100], 'enabled': False, 'priority': moderation_repository.next_moderation_rule_priority(guild_id, family)})
        return _serialize_rule_resource_ids(moderation_repository.save_moderation_rule(guild_id, validate_rule(copy)))

    @router.post('/guilds/{guild_id}/moderation/{family}/preview', dependencies=[Depends(auth.csrf)], response_model=schemas.RulePreview, response_model_exclude_unset=True, openapi_extra=request_schema(inputs.RulePreviewInput))
    async def preview(request: Request, guild_id: int, family: str, _access: str=Depends(auth.read)) -> dict[str, Any]:
        body = await read_body(request, inputs.RulePreviewInput)
        try:
            value = normalized_rule(body.get('rule', {}), family)
            test = body.get('input', {})
            context = MessageContext(guild_id, 1, int(test.get('channel_id') or 1), content=str(test.get('content', ''))[:4000], mention_count=max(0, min(int(test.get('mentions', 0)), 100)), attachment_count=max(0, min(int(test.get('attachments', 0)), 20)), sticker_count=max(0, min(int(test.get('stickers', 0)), 100)), event_type=value['event_type'])
            engine, matches = (AutoModEngine(), [])
            repeats = int(value['trigger_config'].get('limit', 1)) if value['trigger_type'].endswith('rate') or value['trigger_type'] in {'duplicate', 'reaction_burst', 'new_account_ratio', 'emoji_sticker_rate'} else 1
            for _ in range(max(1, min(repeats, 100))):
                matches = await engine.evaluate(context, [{**value, 'id': 1, 'enabled': True}])
            return {'matched': bool(matches), 'reason': matches[0].reason if matches else '一致しませんでした。', 'trace': ['actor', 'global_exemptions', 'family_exemptions', 'rule_exemptions', 'conditions', 'trigger']}
        except (TypeError, ValueError) as exc:
            raise api_error(422, 'preview_invalid', 'ルールまたはテスト入力を確認してください。') from exc



    return router
