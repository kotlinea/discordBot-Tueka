"""Common exemption-list shape; feature defaults belong to their modules."""
def normalize(settings, extra=None):
    defaults = {'log_channel_id': None, 'immune_role_ids': [], 'immune_user_ids': [], 'immune_channel_ids': []}
    defaults.update(extra or {})
    defaults.update(settings)
    for key in ('immune_role_ids', 'immune_user_ids', 'immune_channel_ids'):
        defaults[key] = list(dict.fromkeys(int(value) for value in defaults.get(key, []) if str(value).isdigit()))[:100]
    return defaults
