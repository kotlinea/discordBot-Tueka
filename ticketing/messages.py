"""Ticket message values; no Discord SDK objects cross the service boundary."""
from datetime import datetime, timezone


def bounded_embed(value):
    """Fit rendered previews and their receipt footer into one Discord embed."""
    result = dict(value)
    remaining = 6000
    # Reserve the receipt before fitting visible text so recovery can still find it.
    for kind, field, maximum in (('footer', 'text', 2048), ('author', 'name', 256)):
        if result.get(kind):
            part = dict(result[kind])
            part[field] = str(part.get(field) or '')[:maximum]
            remaining -= len(part[field])
            result[kind] = part
    result['title'] = str(result.get('title') or '')[:256]
    remaining -= len(result['title'])
    fields = list(result.get('fields') or [])[:25]
    fitted = []
    for index, field in enumerate(fields):
        # Keep at least a name and value for every remaining preview field.
        reserve = (len(fields) - index - 1) * 2
        name = str(field.get('name') or '-')[:min(256, remaining - reserve - 1)]
        content = str(field.get('value') or '-')[:min(1024, remaining - reserve - len(name))]
        fitted.append({**field, 'name': name, 'value': content})
        remaining -= len(name) + len(content)
    result['fields'] = fitted
    result['description'] = str(result.get('description') or '')[:min(4096, remaining)]
    return result


def welcome(ticket, panel, member, team, answers):
    replacements = {'ticket_number': ticket['ticket_number'], 'user': f"<@{member['id']}>",
        'username': member['name'], 'user_id': member['id'], 'panel': panel['name'], 'team': (team or {}).get('name', 'Support')}
    def render(value):
        value = str(value or '')
        for key, replacement in replacements.items():
            value = value.replace('{' + key + '}', str(replacement))
        return value
    config = panel.get('welcome_embed') or {}
    embed = {'title': render(config.get('title')), 'description': render(config.get('description')),
             'color': int(str(config.get('color') or '#5865F2').lstrip('#'), 16)}
    if config.get('title_url'):
        embed['url'] = config['title_url']
    if config.get('footer', {}).get('timestamp'):
        embed['timestamp'] = datetime.now(timezone.utc).isoformat()
    for kind, field in (('author', 'name'), ('footer', 'text')):
        value = config.get(kind) or {}
        if value.get('enabled') and value.get(field):
            embed[kind] = {key: val for key, val in value.items() if key in {'name', 'text', 'url', 'icon_url'} and val}
            embed[kind][field] = render(value[field])
    for kind in ('image', 'thumbnail'):
        if config.get(kind + '_url'):
            embed[kind] = {'url': config[kind + '_url']}
    answer_fields = [{'name': key[:256], 'value': value[:1024] or '-', 'inline': False} for key, value in answers.items()][:25]
    embed['fields'] = answer_fields + [
        {'name': render(field['name']), 'value': render(field['value']), 'inline': bool(field.get('inline'))}
        for field in config.get('fields', [])[:25 - len(answer_fields)]]
    embed = bounded_embed(embed)
    buttons = []
    for enabled, label, action, style in (
        (panel.get('show_claim_button') and panel['mode'] == 'channel', 'Claim', 'claim', 2),
        (panel['mode'] == 'private_thread', '参加', 'join', 2),
        (panel.get('show_close_button'), 'Close', 'close', 4),
        (panel.get('show_close_reason_button'), '理由を入力してClose', 'close-reason', 2),
        (panel.get('awaiting_category_id') and panel['mode'] == 'channel', '回答待ち', 'awaiting', 2)):
        if enabled:
            buttons.append({'label': label, 'custom_id': f"tueka-ticket:{action}:{ticket['id']}", 'style': style})
    roles = panel.get('mention_role_ids', [])
    return {'channel_id': ticket['discord_container_id'], 'content': ' '.join([f"<@{member['id']}>"] + [f'<@&{role}>' for role in roles]),
            'embed': embed, 'buttons': buttons, 'user_ids': [member['id']], 'role_ids': roles}


def close_notice(ticket, panel, transcript, base, *, direct):
    link = f"{base.rstrip('/')}/tickets/transcripts/{transcript['id']}" if base else None
    if direct:
        buttons = [{'label': 'Transcript', 'style': 5, 'url': link}] if link else []
        if panel.get('feedback_enabled'):
            buttons.extend({'label': str(rating), 'style': 2, 'custom_id': f"tueka-ticket-feedback:{ticket['id']}:{rating}"} for rating in range(1, 6))
        return {'user_id': ticket['opener_id'], 'content': f"Ticket #{ticket['ticket_number']} をCloseしました。", 'buttons': buttons}
    label = f"[Transcript #{transcript['id']}]({link})" if link else f"Transcript #{transcript['id']}"
    return {'content': f"Ticket #{ticket['ticket_number']} · {panel.get('name', 'Ticket')} · {label}\nClose理由: {str(ticket.get('close_reason') or '')[:1000]}"}
