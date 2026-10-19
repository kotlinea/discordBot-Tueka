"""Pure intake and review policies evaluated under the repository transaction lock."""
from .models import can_submit, validate_answers


def intake(form, answers, *, revision, roles, created_at, joined_at, now):
    if not form['enabled']:
        raise PermissionError('form_disabled')
    if form['revision'] != revision:
        raise RuntimeError('form_changed')
    if not can_submit(form,roles,created_at=created_at,joined_at=joined_at,now=now):
        raise PermissionError('access_denied')
    return validate_answers(form,answers)


def review_transition(row, actor, status, reason, *, revision, withdraw=False):
    if (not reason.strip() or len(reason)>1000) and not withdraw:
        raise ValueError('reason_required')
    if (withdraw and status!='withdrawn') or (not withdraw and status not in ('reviewing','approved','rejected')):
        raise ValueError('invalid_status')
    if row['revision'] != revision or row['status'] not in ('pending','reviewing') or row['status']==status:
        raise RuntimeError('revision_or_status_conflict')
    if (withdraw and row['author_id'] != actor) or (not withdraw and row['author_id']==actor):
        raise PermissionError('review_forbidden')
