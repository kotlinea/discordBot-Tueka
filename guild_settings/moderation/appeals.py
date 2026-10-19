"""Appeals retention defaults and validation."""
def normalize(values):
    value=(values or {}).get('retention_days',30)
    if type(value) is not int or not 1 <= value <= 365:
        raise ValueError('retention_days must be between 1 and 365')
    return {'retention_days':value}
