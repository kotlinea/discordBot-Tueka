"""Bounded form definitions, answers and access policy; no transport dependencies."""
import re


def integer(value, low, high):
    if isinstance(value, bool):
        raise ValueError('invalid_integer')
    result = int(value)
    if str(result) != str(value) or not low <= result <= high:
        raise ValueError('invalid_integer')
    return result


def ids(values):
    if not isinstance(values, list) or len(values) > 25:
        raise ValueError('invalid_roles')
    result = [integer(v, 1, 2**63-1) for v in values]
    if len(set(result)) != len(result):
        raise ValueError('duplicate_roles')
    return result


def validate_form(raw):
    title = str(raw.get('title', '')).strip()
    description = str(raw.get('description', '')).strip()
    if not 1 <= len(title) <= 45 or len(description) > 2000:
        raise ValueError('invalid_form_title')
    fields = raw.get('fields', [])
    if not isinstance(fields, list) or not 1 <= len(fields) <= 5:
        raise ValueError('invalid_fields')
    normalized, keys = [], set()
    for field in fields:
        key, label = str(field.get('key', '')), str(field.get('label', '')).strip()
        if not re.fullmatch(r'[a-z][a-z0-9_]{0,39}', key) or key in keys or not 1 <= len(label) <= 45:
            raise ValueError('invalid_field')
        style = field.get('style', 'paragraph')
        if style not in ('short', 'paragraph') or not isinstance(field.get('required', True), bool):
            raise ValueError('invalid_field')
        minimum = integer(field.get('min_length', 1), 0, 4000)
        maximum = integer(field.get('max_length', 1000), max(1, minimum), 4000)
        keys.add(key)
        normalized.append(dict(key=key, label=label, style=style, required=field.get('required', True), min_length=minimum, max_length=maximum))
    enabled = raw.get('enabled', False)
    if not isinstance(enabled, bool):
        raise ValueError('invalid_enabled')
    return dict(title=title, description=description, fields=normalized, enabled=enabled,
                required_role_ids=ids(raw.get('required_role_ids', [])), denied_role_ids=ids(raw.get('denied_role_ids', [])),
                account_age_days=integer(raw.get('account_age_days', 0), 0, 3650),
                member_age_days=integer(raw.get('member_age_days', 0), 0, 3650),
                cooldown_seconds=integer(raw.get('cooldown_seconds', 3600), 0, 2592000),
                retention_days=integer(raw.get('retention_days', 30), 1, 365))


def validate_answers(form, answers):
    if not isinstance(answers, dict) or set(answers) - {f['key'] for f in form['fields']}:
        raise ValueError('invalid_answers')
    result = {}
    for field in form['fields']:
        text = answers.get(field['key'], '')
        if not isinstance(text, str):
            raise ValueError('invalid_answer')
        text = text.strip()
        if (field['required'] and not text) or (text and not field['min_length'] <= len(text) <= field['max_length']):
            raise ValueError('invalid_answer_length')
        result[field['key']] = text
    return result


def can_submit(form, roles, *, created_at, joined_at, now):
    roles = set(roles)
    return (not roles.intersection(form['denied_role_ids'])
            and (not form['required_role_ids'] or bool(roles.intersection(form['required_role_ids'])))
            and created_at is not None and created_at <= now - form['account_age_days'] * 86400
            and joined_at is not None and joined_at <= now - form['member_age_days'] * 86400)
