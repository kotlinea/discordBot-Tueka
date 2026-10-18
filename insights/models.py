"""Pure collection settings, bounded UTC periods and observed time segments."""
from datetime import date, datetime, timedelta, timezone
import hashlib
import re

DAY = 86400
MAX_GAP = 90
MAX_TIMESTAMP = 253402300799


def integer(value, field, minimum, maximum):
    if type(value) is not int or not minimum <= value <= maximum:
        raise ValueError(field)
    return value


def snowflake(value):
    if isinstance(value, str) and re.fullmatch(r'[1-9][0-9]{0,18}', value):
        value = int(value)
    return integer(value, 'channel_id', 1, 2**63 - 1)


def normalize(raw):
    if not isinstance(raw, dict) or set(raw) - {'channel_ids', 'retention_days', 'track_members'}:
        raise ValueError('insights_settings')
    channels = raw.get('channel_ids', [])
    if not isinstance(channels, list) or len(channels) > 25:
        raise ValueError('channel_ids')
    track_members = raw.get('track_members', True)
    if type(track_members) is not bool:
        raise ValueError('track_members')
    return {'channel_ids': sorted({snowflake(channel) for channel in channels}),
            'retention_days': integer(raw.get('retention_days', 30), 'retention_days', 1, 365),
            'track_members': track_members}


def timestamp(value):
    return integer(value, 'timestamp', 0, MAX_TIMESTAMP)


def day_key(value):
    return datetime.fromtimestamp(timestamp(value), timezone.utc).date().isoformat()


def period(start, end, now, retention_days):
    """Inclusive UTC dates, maximum 90, wholly inside the current retention window."""
    retention_days = integer(retention_days, 'retention_days', 1, 365)
    values = []
    for raw in (start, end):
        if not isinstance(raw, str) or not re.fullmatch(r'[0-9]{4}-[0-9]{2}-[0-9]{2}', raw):
            raise ValueError('period_date')
        try:
            values.append(date.fromisoformat(raw))
        except ValueError:
            raise ValueError('period_date') from None
    first, last = values
    today = date.fromisoformat(day_key(now))
    if first > last or (last - first).days >= 90 or last > today:
        raise ValueError('period_range')
    if first < today - timedelta(days=retention_days - 1):
        raise ValueError('period_retention')
    return [(first + timedelta(days=offset)).isoformat() for offset in range((last - first).days + 1)]


def segments(start, end):
    """Partition a continuously observed interval; an excessive gap is unknown time."""
    start, end = timestamp(start), timestamp(end)
    if end < start:
        raise ValueError('clock_reversed')
    if end - start > MAX_GAP:
        return []
    result = []
    while start < end:
        stop = min(end, (start // DAY + 1) * DAY)
        result.append((day_key(start), stop - start))
        start = stop
    return result


def membership_key(kind, user_id, joined_at):
    """Deduplicate one observed membership lifetime without storing a plaintext user ID."""
    if kind not in ('join', 'leave'):
        raise ValueError('membership_kind')
    user_id = snowflake(user_id)
    joined_at = integer(joined_at, 'joined_at_microseconds', 0, MAX_TIMESTAMP * 1000000)
    return hashlib.sha256(f'{kind}:{user_id}:{joined_at}'.encode('ascii')).hexdigest()
