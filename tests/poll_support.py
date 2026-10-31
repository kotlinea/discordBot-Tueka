"""Published-poll fixtures and historical test names; production uses draft publication."""
import json
from database import transaction
from engagement.polls.repository import PollRepository
from engagement.polls.models import normalize,PollError


class PublishedPollRepository(PollRepository):
    def create_poll(self,message,guild,channel,creator,question,options,image,closes_at):
        self.settings.set_module(guild,'advanced_polls',enabled=True)
        config=normalize(dict(question=question,options=options,image_url=image))
        with transaction(self.database_url) as c:
            c.execute('''INSERT INTO polls(message_id,guild_id,channel_id,creator_id,question,options_json,image_url,closes_at,created_at,published_at,config_json)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                (message,guild,channel,creator,question,json.dumps(options),image,closes_at,int(self.clock()),int(self.clock()),json.dumps(config)))

    legacy_create=create_poll
    poll=PollRepository.by_message
    poll_display=PollRepository.by_message
    pending_poll_displays=PollRepository.pending_displays
    mark_poll_display_synced=PollRepository.ack_display
    close_expired_polls=PollRepository.close_expired

    def cast_poll_vote(self,message,user,index):
        poll=self.by_message(message)
        if not poll:return None
        try:return self.vote(poll['guild_id'],poll['id'],user,[index],message_id=message)['counts']
        except PollError:return None
