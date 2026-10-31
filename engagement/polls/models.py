"""Poll input, voting eligibility and disclosure rules."""
import re
from dataclasses import dataclass
from urllib.parse import urlsplit
from discord_io.emoji import is_unicode_emoji

FIELDS = ('counts', 'ranking', 'total', 'participants', 'ballots')
LEVELS = {'hidden': 0, 'admins': 1, 'everyone': 2}
MAX_DURATION = 30 * 86400


@dataclass(frozen=True)
class Actor:
    guild_id: int
    user_id: int
    roles: tuple = ()
    manager: bool = False
    bot: bool = False


def permissions(actor, settings):
    if actor.bot:
        return set()
    if actor.manager:
        return {'view', 'manage', 'view_votes', 'manage_votes', 'settings', 'weights', 'permissions'}
    result = {p for role in actor.roles for p in settings['role_permissions'].get(str(role), [])}
    return result | {'view'} if result else set()


class PollError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def duration(value):
    if not isinstance(value, str) or not value.strip():
        raise PollError('invalid')
    parts = re.findall(r'(\d+)\s*([dhms])', value.strip())
    if not parts or re.sub(r'\d+\s*[dhms]|\s+', '', value) or len({unit for _, unit in parts}) != len(parts):
        raise PollError('invalid')
    result = sum(int(n) * {'d': 86400, 'h': 3600, 'm': 60, 's': 1}[u] for n, u in parts)
    if not 1 <= result <= MAX_DURATION:
        raise PollError('invalid')
    return result


def policy(mode='anonymous', custom=None):
    values = {
        'public': ({field: 'everyone' for field in FIELDS}, {field: 'everyone' for field in FIELDS}),
        'anonymous': (dict.fromkeys(FIELDS[:3], 'everyone'), dict.fromkeys(FIELDS[:3], 'everyone')),
        'secret_winner': ({'participants': 'everyone'}, dict.fromkeys(FIELDS, 'everyone')),
        'reveal_at_end': ({}, dict.fromkeys(FIELDS, 'everyone')),
        'blind': ({}, dict.fromkeys(FIELDS[:3], 'everyone')),
    }
    if mode == 'custom':
        if not isinstance(custom, dict) or set(custom) != {'open', 'closed'}:
            raise PollError('invalid')
        stages = [custom['open'], custom['closed']]
    elif mode in values:
        stages = values[mode]
    else:
        raise PollError('invalid')
    result = {}
    for stage, raw in zip(('open', 'closed'), stages):
        if not isinstance(raw, dict) or set(raw) - set(FIELDS):
            raise PollError('invalid')
        result[stage] = {field: raw.get(field, 'hidden') for field in FIELDS}
        if any(value not in LEVELS for value in result[stage].values()):
            raise PollError('invalid')
        if LEVELS[result[stage]['ballots']] > LEVELS[result[stage]['participants']]:
            raise PollError('invalid')
    return result


def text(value, maximum, *, required=False):
    if not isinstance(value, str) or len(value) > maximum or (required and not value.strip()):
        raise PollError('invalid')
    return value.strip()


def emoji(value):
    value = text(value, 100)
    if value and not is_unicode_emoji(value) and not re.fullmatch(r'<a?:[A-Za-z0-9_]{2,32}:\d{1,20}>',value):
        raise PollError('invalid')
    return value


def ids(values):
    if not isinstance(values, list) or len(values) > 100:
        raise PollError('invalid')
    result = []
    for value in values:
        if isinstance(value, bool) or not str(value).isascii() or not str(value).isdecimal() or not 0 < int(value) < 2**63:
            raise PollError('invalid')
        result.append(str(int(value)))
    return sorted(set(result))


def new_condition_roles(config, previous=None):
    """Only newly introduced references in each condition need existence validation."""
    previous = previous or {}
    return {role for field in ('allowed_roles', 'denied_roles')
            for role in set(ids(config.get(field, []))) - set(ids(previous.get(field, [])))}


def normalize(values, *, option_limit=25):
    question = text(values.get('question'), 1024, required=True)
    options = values.get('options')
    if not isinstance(options, list) or not 2 <= len(options) <= option_limit:
        raise PollError('invalid')
    options = [text(item, 256, required=True) for item in options]
    maximum = values.get('max_choices', 1)
    if type(maximum) is not int or not 1 <= maximum <= min(20, len(options)):
        raise PollError('invalid')
    image = values.get('image_url') or None
    if image:
        image = text(image, 2048)
        parsed = urlsplit(image)
        if parsed.scheme not in ('http', 'https') or not parsed.netloc or parsed.username or parsed.password:
            raise PollError('invalid')
    mode = values.get('mode', 'anonymous')
    ui = values.get('ui', 'buttons')
    if ui not in ('buttons', 'select'):
        raise PollError('invalid')
    button_style=values.get('button_style','secondary')
    if button_style not in ('primary','secondary','success','danger'):raise PollError('invalid')
    color = values.get('color', 0x5865F2)
    cap = values.get('max_participants')
    if type(color) is not int or not 0 <= color <= 0xFFFFFF or (cap is not None and (type(cap) is not int or not 1 <= cap <= 1000000)):
        raise PollError('invalid')
    emojis = values.get('emojis', [''] * len(options))
    if not isinstance(emojis, list) or len(emojis) != len(options):
        raise PollError('invalid')
    flags = {key: values.get(key, False) for key in ('announce_winner','pin_on_close','create_thread','remove_departed_votes')}
    if any(type(value) is not bool for value in flags.values()):
        raise PollError('invalid')
    return dict(question=question, description=text(values.get('description', ''), 2000), options=options, **flags,
                max_choices=maximum, mode=mode, visibility=policy(mode, values.get('visibility')),
                ui='select' if len(options) > 20 else ui, button_style=button_style, image_url=image, color=color,
                emojis=[emoji(item) for item in emojis], max_participants=cap,
                allowed_roles=ids(values.get('allowed_roles', [])), denied_roles=ids(values.get('denied_roles', [])),
                denied_users=ids(values.get('denied_users', [])))


def selection(values, count, maximum):
    if not isinstance(values, list) or any(type(value) is not int or not 0 <= value < count for value in values):
        raise PollError('invalid')
    if len(values) != len(set(values)) or len(values) > maximum:
        raise PollError('invalid')
    return sorted(values)


def eligible(config, user, roles, *, bot=False):
    roles = {str(role) for role in roles}
    return not (bot or str(user) in config['denied_users'] or roles.intersection(config['denied_roles'])) and (
        not config['allowed_roles'] or bool(roles.intersection(config['allowed_roles'])))


def weight(weights, roles):
    return max([1] + [weights.get(str(role), 1) for role in roles])


def preserve_privacy(original, updated):
    if any(LEVELS[updated[stage][field]] > LEVELS[original[stage][field]] for stage in original for field in FIELDS):
        raise PollError('privacy_expansion')


def disclose(poll, *, admin=False, view_votes=False):
    """Produce an allowlist projection; private source fields never reach callers."""
    stage = 'closed' if poll['status'] in ('closed', 'deleted') else 'open'
    rules = poll['config']['visibility'][stage]
    def visible(field):
        return rules[field] == 'everyone' or (rules[field] == 'admins' and admin)
    result = {key: poll.get(key) for key in ('id', 'message_id', 'guild_id', 'channel_id', 'status', 'revision', 'closes_at', 'created_at', 'scheduled_at', 'duration_seconds', 'published_at')}
    for key in ('message_id','guild_id','channel_id'):
        if result[key] is not None:result[key]=str(result[key])
    config = poll['config']
    result['config'] = {key: config[key] for key in ('question', 'description', 'options', 'emojis', 'max_choices', 'mode', 'visibility', 'ui', 'image_url', 'color', 'max_participants', 'allowed_roles','button_style')}
    if visible('counts'):
        result['counts'] = poll['counts']
        result['weighted_counts'] = poll['weighted_counts']
    if visible('ranking'):
        scores = poll['weighted_counts']
        result['ranking'] = [1 + sum(other > score for other in scores) for score in scores]
    if visible('total'):
        result['total'] = poll['total']
        result['selections'] = sum(poll['counts'])
    if visible('participants') and (rules['participants'] == 'everyone' or view_votes):
        result['participants'] = [str(row['user_id']) for row in poll['ballots']]
    if visible('ballots') and (rules['ballots'] == 'everyone' or view_votes):
        result['ballots'] = [dict(user_id=str(row['user_id']), choices=row['choices'], weight=row['weight']) for row in poll['ballots']]
    return result
