"""Poll retention, role weights and delegated permissions."""
PERMISSIONS = {'view', 'manage', 'view_votes', 'manage_votes', 'settings', 'weights'}


def normalize(values):
    values = values or {}
    days = values.get('retention_days', 90)
    if type(days) is not int or not 1 <= days <= 365:
        raise ValueError('retention_days')
    weights = values.get('role_weights', {})
    grants = values.get('role_permissions', {})
    if not isinstance(weights, dict) or not isinstance(grants, dict) or len(weights) > 100 or len(grants) > 100:
        raise ValueError('role_settings')
    for role, value in weights.items():
        if not isinstance(role, str) or not role.isascii() or not role.isdecimal() or int(role) <= 0 or type(value) is not int or not 1 <= value <= 100:
            raise ValueError('role_weights')
    for role, value in grants.items():
        if not isinstance(role, str) or not role.isascii() or not role.isdecimal() or int(role) <= 0 or not isinstance(value, list) or any(item not in PERMISSIONS for item in value):
            raise ValueError('role_permissions')
    return {'retention_days': days, 'role_weights': dict(weights), 'role_permissions': {role: sorted(set(value)) for role, value in grants.items()}}
