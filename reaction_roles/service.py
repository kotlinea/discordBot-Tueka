"""Discord-independent Reaction Role decisions and orchestration helpers."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .models import ReactionRoleValidationError, validate_message
from .repository import ReactionRoleRepository


@dataclass
class ReactionDecision:
    allowed: bool
    operation: str = "none"
    reason: str = ""
    conflicting_assignments: list[dict[str, Any]] = field(default_factory=list)


def preserves_linked_selection(repository, config: dict, mapping: dict, user_id: int) -> bool:
    if not config.get('link_group_id'):
        return False
    active = repository.assignments(user_id, link_group_id=config['link_group_id'], guild_id=config['guild_id'])
    if any(item['message_config_id'] == config['id'] and item['mapping_id'] == mapping['id'] for item in active):
        return False
    return any(item['role_id'] == mapping['role_id'] for item in active)


class ReactionRoleService:
    def __init__(self, repository: ReactionRoleRepository, *, max_mappings: int = 20) -> None:
        self.repository, self.max_mappings = repository, max_mappings

    def validate(self, raw: dict[str, Any]) -> dict[str, Any]:
        return validate_message(raw, max_mappings=self.max_mappings)

    def decide(self, config: dict[str, Any], mapping: dict[str, Any], *, event: str, user_id: int,
               member_role_ids: set[int], role_member_count: int = 0) -> ReactionDecision:
        if not config.get("enabled"):
            return ReactionDecision(False, reason="この設定は無効です。")
        if config.get("locked"):
            return ReactionDecision(False, reason="このReaction Roleは停止中です。")
        behavior = config["behavior_type"]
        operation = {
            ("normal", "add"): "add", ("normal", "remove"): "remove",
            ("unique", "add"): "add", ("unique", "remove"): "remove",
            ("verify", "add"): "add", ("binding", "add"): "add",
            ("drop", "add"): "remove",
            ("reversed", "add"): "remove", ("reversed", "remove"): "add",
            ("temp", "add"): "add", ("temp", "remove"): "remove",
        }.get((behavior, event), "none")
        if operation == "none": return ReactionDecision(True, operation="none")
        if operation == "remove":
            if event == 'remove' and behavior in {'normal', 'unique', 'temp'}:
                if preserves_linked_selection(self.repository, config, mapping, user_id):
                    return ReactionDecision(True, operation='none')
            return ReactionDecision(True, operation="remove")
        blacklist=set(config.get("blacklist_role_ids",[])); whitelist=set(config.get("whitelist_role_ids",[]))
        if blacklist & member_role_ids: return ReactionDecision(False, reason="このReaction Roleは利用できません。")
        if whitelist and not whitelist & member_role_ids: return ReactionDecision(False, reason="必要なRoleを持っていません。")
        if behavior == "binding" and self.repository.binding_receipt(config["id"],user_id):
            return ReactionDecision(False,reason="この選択はすでに確定しています。")
        conflicts=self.repository.assignments(user_id,link_group_id=config.get("link_group_id"),guild_id=config['guild_id']) if config.get("link_group_id") else self.repository.assignments(user_id,config_id=config["id"])
        conflicts=[item for item in conflicts if int(item["mapping_id"])!=int(mapping["id"])]
        limit=config.get("selection_limit")
        if config.get("link_group_id") or behavior in {"unique","binding"}: limit=1
        if limit and len(conflicts)>=int(limit):
            if behavior in {"unique"} or config.get("link_group_id"): pass
            else:return ReactionDecision(False,reason=f"このメッセージでは最大{limit}個まで選択できます。")
        cap=mapping.get("max_members")
        if cap and mapping["role_id"] not in member_role_ids and role_member_count>=int(cap):
            return ReactionDecision(False,reason="このRoleは人数上限に達しています。")
        return ReactionDecision(True,operation="add",conflicting_assignments=conflicts if (behavior=="unique" or config.get("link_group_id")) else [])

    @staticmethod
    def mapping(config: dict[str, Any], emoji_key: str) -> dict[str, Any] | None:
        return next((item for item in config.get("mappings",[]) if item.get("emoji_key")==emoji_key),None)

    def create(self,guild_id:int,raw:dict[str,Any],actor_id:int|None=None)->dict[str,Any]:
        return self.repository.create_message(guild_id,self.validate(raw),actor_id)

    def update(self,guild_id:int,config_id:int,raw:dict[str,Any],revision:int,actor_id:int|None=None)->dict[str,Any]:
        return self.repository.update_message(guild_id,config_id,self.validate(raw),revision,actor_id)

    def preview(self,raw:dict[str,Any])->dict[str,Any]:
        value=self.validate(raw)
        return {"valid":True,"normalized":value,"diagnostics":[{"level":"info","message":f"{len(value['mappings'])}件の対応を確認しました。"}]}
