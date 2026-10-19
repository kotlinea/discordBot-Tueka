"""Host-independent schedule validation; timestamps are Unix UTC seconds."""
from urllib.parse import urlparse


def integer(value, name, low, high):
    if type(value) is not int or not low <= value <= high:
        raise ValueError(name)
    return value


def short(value, name, maximum, *, required=False):
    if not isinstance(value, str) or len(value.strip()) > maximum or required and not value.strip():
        raise ValueError(name)
    return value.strip()


def normalize(values, now):
    """Validate the entire immutable occurrence payload before reserving work."""
    kind = values.get('kind')
    if kind not in ('message', 'event'):
        raise ValueError('kind')
    run_at = integer(values.get('run_at'), 'run_at', now + 30, now + 365 * 86400)
    interval = integer(values.get('interval_seconds', 0), 'interval_seconds', 0, 604800)
    if interval not in (0, 86400, 604800):
        raise ValueError('interval_seconds')
    count = integer(values.get('occurrences', 1), 'occurrences', 1, 365)
    if (not interval and count != 1) or (run_at + interval * (count - 1) > now + 365 * 86400):
        raise ValueError('occurrences')
    title = short(values.get('title', ''), 'title', 100, required=kind == 'event')
    body = short(values.get('body', ''), 'body', 2000, required=not title)
    color = integer(values.get('color', 0x5865F2), 'color', 0, 0xFFFFFF)
    result = dict(kind=kind, title=title, body=body, color=color, run_at=run_at,
                  interval_seconds=interval, occurrences=count)
    if kind == 'message':
        result['channel_id'] = integer(values.get('channel_id'), 'channel_id', 1, 2**63 - 1)
    else:
        if interval or count != 1:
            raise ValueError('event_recurrence')
        start = integer(values.get('event_start'), 'event_start', run_at + 60, now + 366 * 86400)
        end = integer(values.get('event_end'), 'event_end', start + 60, start + 7 * 86400)
        location = short(values.get('event_location', ''), 'event_location', 100, required=True)
        # Discord accepts plain external locations; do not fetch URLs server-side.
        if '://' in location and urlparse(location).scheme not in ('http', 'https'):
            raise ValueError('event_location')
        result.update(event_start=start, event_end=end, event_location=location)
    return result
