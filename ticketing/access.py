"""Ticket team membership contract shared by HTTP entry points."""
from typing import Any


def team_member(team: dict[str, Any], user_id: int, member: dict[str, Any] | None) -> bool:
    """An explicit team assignment never grants access after guild membership ends."""
    if member is None:
        return False
    roles = {int(item) for item in member.get('roles', [])}
    return bool(user_id in team.get('user_ids', []) or user_id in team.get('admin_user_ids', [])
                or roles.intersection(team.get('role_ids', [])))
