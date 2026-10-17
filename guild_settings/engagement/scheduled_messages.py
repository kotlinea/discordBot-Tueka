"""History retention is captured when a schedule is created."""


def normalize(values):
    value = (values or {}).get('retention_days', 30)
    if type(value) is not int or not 1 <= value <= 365:
        raise ValueError('retention_days')
    return {'retention_days': value}
