"""Content-free Gateway inputs translated into aggregate observations."""
import uuid

from .models import membership_key


class InsightsService:
    def __init__(self, repository, *, owner=None):
        self.repository = repository
        self.owner = uuid.uuid4().hex if owner is None else owner

    def claim(self, guild):
        return self.repository.claim(guild, self.owner)

    def release(self, guild):
        return self.repository.release(guild, self.owner)

    def heartbeat(self, guild, voice):
        return self.repository.heartbeat(guild, self.owner, voice)

    def message(self, guild, message, channel, created_at, *, bot=False):
        if bot is not False:
            return False
        # No message body, author name, attachment or embed crosses this boundary.
        from .models import snowflake
        message = snowflake(message)
        return self.repository.event(guild, self.owner, 'messages', str(message), channel=channel, occurred_at=created_at)

    def membership(self, guild, user, joined_at, *, joining, bot=False):
        if bot is not False or joined_at is None:
            return False
        if type(joining) is not bool:
            raise ValueError('membership_action')
        action = 'join' if joining else 'leave'
        values = {'occurred_at': joined_at // 1000000} if joining else {}
        return self.repository.event(guild, self.owner, 'joins' if joining else 'leaves', membership_key(action, user, joined_at), **values)

    def voice(self, guild, user, before, after, *, bot=False):
        if bot is not False:
            return False
        return self.repository.voice_change(guild, self.owner, user, before, after)
