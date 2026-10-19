"""Pure campaign validation, eligibility and cryptographic winner selection."""
import hashlib
import json
from secrets import SystemRandom


def integer(value, name, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(f'invalid_{name}')
    return value


def snowflake(value, name):
    if isinstance(value, str) and value.isascii() and value.isdigit():
        value = int(value)
    return integer(value, name, 1, 2**63 - 1)


def text(value, name, limit, *, required=True):
    if not isinstance(value, str) or len(value.strip()) > limit:
        raise ValueError(f'invalid_{name}')
    value = value.strip()
    if (required and not value) or any(ord(c) < 32 and c not in '\n\t' for c in value):
        raise ValueError(f'invalid_{name}')
    return value


def role_ids(values, name):
    if not isinstance(values, list) or len(values) > 25:
        raise ValueError(f'invalid_{name}')
    return list(dict.fromkeys(snowflake(v, name) for v in values))


def normalize(values, now):
    if not isinstance(values, dict):
        raise ValueError('invalid_campaign')
    kind = values.get('kind', 'giveaway')
    if kind not in ('giveaway', 'event'):
        raise ValueError('invalid_kind')
    required = role_ids(values.get('required_role_ids', []), 'required_role_ids')
    denied = role_ids(values.get('denied_role_ids', []), 'denied_role_ids')
    if set(required) & set(denied):
        raise ValueError('conflicting_roles')
    winners = integer(values.get('winner_count', 1 if kind == 'giveaway' else 0), 'winner_count', 0, 20)
    if (kind == 'event' and winners != 0) or (kind == 'giveaway' and winners == 0):
        raise ValueError('invalid_winner_count')
    return {
        'kind': kind,
        'title': text(values.get('title'), 'title', 120),
        'description': text(values.get('description', ''), 'description', 2000, required=False),
        'channel_id': snowflake(values.get('channel_id'), 'channel_id'),
        'ends_at': integer(values.get('ends_at'), 'ends_at', now + 30, now + 90 * 86400),
        'winner_count': winners,
        'capacity': integer(values.get('capacity', 1000), 'capacity', 1, 1000),
        'required_role_ids': required,
        'denied_role_ids': denied,
        'min_account_days': integer(values.get('min_account_days', 0), 'min_account_days', 0, 3650),
        'min_member_days': integer(values.get('min_member_days', 0), 'min_member_days', 0, 3650),
        'retention_days': integer(values.get('retention_days', 30), 'retention_days', 1, 365),
    }


def eligible(config, member, guild, now):
    if not member or member.get('guild_id') != guild or member.get('bot'):
        return False
    roles = set(member.get('role_ids', []))
    if roles & set(config['denied_role_ids']):
        return False
    if config['required_role_ids'] and not roles & set(config['required_role_ids']):
        return False
    for field, days in (('created_at', 'min_account_days'), ('joined_at', 'min_member_days')):
        timestamp = member.get(field)
        if type(timestamp) is not int or timestamp > now or now - timestamp < config[days] * 86400:
            return False
    return True


def selection(candidates, count, *, previous=(), rng=None):
    pool = sorted(set(candidates) - set(previous))
    for user in pool:
        snowflake(user, 'candidate')
    integer(count, 'winner_count', 0, 20)
    winners = (rng or SystemRandom()).sample(pool, min(count, len(pool)))
    digest = hashlib.sha256(json.dumps(pool, separators=(',', ':')).encode()).hexdigest()
    return pool, winners, digest
