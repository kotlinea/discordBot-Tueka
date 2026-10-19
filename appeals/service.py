"""Ownership checks across public domain contracts and pure review rules."""
def parse_guild(value):
    if not isinstance(value,str) or not value.isascii() or not value.isdecimal():
        raise ValueError('invalid_guild')
    result=int(value)
    if not 0 < result < 2**63:raise ValueError('invalid_guild')
    return result


def text(value, maximum=2000):
    if not isinstance(value, str) or not 1 <= len(value.strip()) <= maximum:
        raise ValueError('message_required')
    return value.strip()


def review(item, actor, status, reason, revision):
    text(reason, 1000)
    if status not in ('reviewing', 'accepted', 'rejected', 'closed'):
        raise ValueError('invalid_status')
    if item['revision'] != revision or item['status'] not in ('open', 'reviewing') or status == item['status']:
        raise RuntimeError('revision_or_status_conflict')
    if actor == item['author_id'] or (item['kind'] == 'appeal' and actor == item['original_moderator_id']):
        raise PermissionError('independent_reviewer_required')


class AppealService:
    def __init__(self, repository, moderation, applications, tickets):
        self.repository, self.moderation = repository, moderation
        self.applications, self.tickets = applications, tickets

    def open(self, guild, author, interaction, content, *, case_id=None, application_id=None):
        case = self.moderation.case(guild, case_id) if case_id is not None else None
        if case_id is not None and (not case or case['user_id'] != author):
            raise PermissionError('case_owner_required')
        if application_id is not None:
            application = self.applications.item(guild, application_id, author=author)
            if not application:
                raise PermissionError('application_owner_required')
        return self.repository.open(guild, author, interaction, text(content), case=case, application_id=application_id)

    def link_ticket(self, guild, item_id, actor, ticket_id, revision):
        item = self.repository.item(guild, item_id)
        ticket = self.tickets.ticket(ticket_id) if self.tickets else None
        if not ticket or ticket['guild_id'] != guild or ticket['opener_id'] != item['author_id']:
            raise PermissionError('ticket_owner_required')
        return self.repository.link_ticket(guild, item_id, actor, ticket_id, revision)
