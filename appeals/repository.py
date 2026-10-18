"""Locked private conversations, audit, expiry and atomic DM reservations."""
import time
from database import require_current, transaction, lock_resource
from guild_settings import GuildSettingsRepository
from jobs import QueueRepository
from jobs.catalog import QUEUE_SPECS
from .service import text, review


class AppealQueue(QueueRepository):
    def _claim_scope(self):
        return (' AND EXISTS(SELECT 1 FROM appeal_threads t JOIN guild_modules g ON g.guild_id=t.guild_id'
                ' WHERE t.id=appeal_outbox.thread_id AND g.module_id=%s AND g.enabled=1)', ('appeals',))


class AppealRepository:
    def __init__(self, url):
        self.database_url = url
        require_current(url)
        self.settings = GuildSettingsRepository(url)
        self.jobs = AppealQueue(url, QUEUE_SPECS['appeal_outbox'])

    def _enabled(self, c, guild):
        lock_resource(c, 'guild-module', f'{guild}:appeals')
        module = self.settings.get_module(guild, 'appeals', _conn=c)
        if not module['enabled']:
            raise PermissionError('appeals_disabled')
        return module['settings']

    def _item(self, c, guild, item_id, *, author=None, locked=False):
        row = c.execute('SELECT * FROM appeal_threads WHERE guild_id=%s AND id=%s AND expires_at>%s' + (' FOR UPDATE' if locked else ''),
                        (guild, item_id, int(time.time()))).fetchone()
        if not row or (author is not None and row['author_id'] != author):
            raise LookupError('thread_not_found')
        return row

    @staticmethod
    def _event(c, item_id, actor, event, reason, now):
        return c.execute('INSERT INTO appeal_events(thread_id,actor_id,event_type,reason,created_at) VALUES(%s,%s,%s,%s,%s) RETURNING id', (item_id,actor,event,reason,now)).fetchone()['id']

    @staticmethod
    def _notify(c, item_id, now, message_id=None, event_id=None):
        c.execute('INSERT INTO appeal_outbox(thread_id,message_id,event_id,available_at,created_at) VALUES(%s,%s,%s,%s,%s)', (item_id,message_id,event_id,now,now))

    def open(self, guild, author, interaction, content, *, case=None, application_id=None):
        content, now = text(content), int(time.time())
        with transaction(self.database_url) as c:
            config = self._enabled(c,guild)
            lock_resource(c,'appeal-intake',f'{guild}:{author}')
            old = c.execute('SELECT * FROM appeal_threads WHERE interaction_id=%s', (interaction,)).fetchone()
            if old:
                if old['guild_id'] != guild or old['author_id'] != author:
                    raise PermissionError('interaction_mismatch')
                return self._item(c,guild,old['id'],author=author)
            c.execute('DELETE FROM appeal_threads WHERE guild_id=%s AND author_id=%s AND expires_at<=%s', (guild,author,now))
            case_id = case['id'] if case else None
            if c.execute("SELECT 1 FROM appeal_threads WHERE guild_id=%s AND author_id=%s AND COALESCE(case_id,0)=%s AND status IN ('open','reviewing')", (guild,author,case_id or 0)).fetchone():
                raise RuntimeError('thread_open')
            last = c.execute('SELECT created_at FROM appeal_threads WHERE guild_id=%s AND author_id=%s ORDER BY id DESC LIMIT 1', (guild,author)).fetchone()
            if last and now-last['created_at'] < 60:
                raise RuntimeError('intake_cooldown')
            row = c.execute('INSERT INTO appeal_threads(guild_id,author_id,interaction_id,kind,case_id,original_moderator_id,case_action,application_id,created_at,updated_at,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *',
                (guild,author,interaction,'appeal' if case else 'modmail',case_id,case.get('moderator_id') if case else None,case.get('action') if case else None,application_id,now,now,now+config['retention_days']*86400)).fetchone()
            c.execute('INSERT INTO appeal_messages(thread_id,actor_id,staff,content,interaction_id,created_at) VALUES(%s,%s,0,%s,%s,%s)', (row['id'],author,content,interaction,now))
            self._event(c,row['id'],author,'submitted','',now)
            return row

    def item(self, guild, item_id, *, author=None):
        with transaction(self.database_url) as c:
            return self._item(c,guild,item_id,author=author)

    def items(self, guild, *, author=None, before=None, limit=50):
        with transaction(self.database_url) as c:
            return c.execute('SELECT * FROM appeal_threads WHERE guild_id=%s AND expires_at>%s AND (%s::bigint IS NULL OR author_id=%s) AND (%s::bigint IS NULL OR id<%s) ORDER BY id DESC LIMIT %s',
                (guild,int(time.time()),author,author,before,before,max(1,min(limit,100)))).fetchall()

    def conversation(self, guild, item_id, *, author=None):
        with transaction(self.database_url) as c:
            self._item(c,guild,item_id,author=author)
            return {'messages':c.execute('SELECT id,actor_id,staff,content,created_at FROM appeal_messages WHERE thread_id=%s ORDER BY id LIMIT 100', (item_id,)).fetchall(),
                    'events':c.execute('SELECT id,actor_id,event_type,reason,created_at FROM appeal_events WHERE thread_id=%s ORDER BY id DESC LIMIT 100', (item_id,)).fetchall(),
                    'delivery':c.execute('SELECT id,status,attempts,delivery_started,discord_message_id FROM appeal_outbox WHERE thread_id=%s ORDER BY id DESC LIMIT 100',(item_id,)).fetchall()}

    def reply(self, guild, item_id, actor, content, *, revision, staff=False, interaction=None):
        content, now = text(content), int(time.time())
        with transaction(self.database_url) as c:
            self._enabled(c,guild)
            row = self._item(c,guild,item_id,locked=True)
            if not staff and actor != row['author_id'] or staff and actor == row['author_id']:
                raise PermissionError('reply_forbidden')
            if interaction is not None:
                previous=c.execute('SELECT id,thread_id,actor_id FROM appeal_messages WHERE interaction_id=%s',(interaction,)).fetchone()
                if previous:
                    if previous['thread_id'] != item_id or previous['actor_id'] != actor:
                        raise PermissionError('interaction_mismatch')
                    return row
            if revision != row['revision'] or row['status'] not in ('open','reviewing'):
                raise RuntimeError('revision_or_status_conflict')
            count=c.execute('SELECT COUNT(*) AS n FROM appeal_messages WHERE thread_id=%s',(item_id,)).fetchone()['n']
            if count >= 100:
                raise ValueError('message_limit')
            message=c.execute('INSERT INTO appeal_messages(thread_id,actor_id,staff,content,interaction_id,created_at) VALUES(%s,%s,%s,%s,%s,%s) RETURNING id', (item_id,actor,int(staff),content,interaction,now)).fetchone()
            row=c.execute('UPDATE appeal_threads SET revision=revision+1,updated_at=%s WHERE id=%s RETURNING *',(now,item_id)).fetchone()
            self._event(c,item_id,actor,'staff_reply' if staff else 'reply','',now)
            if staff:self._notify(c,item_id,now,message['id'])
            return row

    def transition(self, guild, item_id, actor, status, reason, *, revision, withdraw=False):
        now=int(time.time())
        with transaction(self.database_url) as c:
            self._enabled(c,guild)
            row=self._item(c,guild,item_id,locked=True)
            if withdraw:
                if actor != row['author_id'] or status != 'withdrawn':raise PermissionError('owner_required')
                if revision != row['revision'] or row['status'] not in ('open','reviewing'):raise RuntimeError('revision_or_status_conflict')
                reason=''
            else:review(row,actor,status,reason,revision)
            row=c.execute('UPDATE appeal_threads SET status=%s,revision=revision+1,updated_at=%s WHERE id=%s RETURNING *',(status,now,item_id)).fetchone()
            event=self._event(c,item_id,actor,status,reason.strip(),now)
            if not withdraw:self._notify(c,item_id,now,event_id=event)
            return row

    def link_ticket(self, guild, item_id, actor, ticket_id, revision):
        now=int(time.time())
        with transaction(self.database_url) as c:
            self._enabled(c,guild)
            row=self._item(c,guild,item_id,locked=True)
            if actor == row['author_id']:raise PermissionError('manager_required')
            if revision != row['revision']:raise RuntimeError('revision_conflict')
            row=c.execute('UPDATE appeal_threads SET ticket_id=%s,revision=revision+1,updated_at=%s WHERE id=%s RETURNING *',(ticket_id,now,item_id)).fetchone()
            self._event(c,item_id,actor,'ticket_linked',str(ticket_id),now)
            return row

    def delivery(self, job):
        with transaction(self.database_url) as c:
            thread=c.execute('SELECT * FROM appeal_threads WHERE id=%s AND expires_at>%s',(job['thread_id'],int(time.time()))).fetchone()
            if not thread:return None
            module=self.settings.get_module(thread['guild_id'],'appeals',_conn=c)
            if not module['enabled']:return None
            if job['message_id']:
                body=c.execute('SELECT content FROM appeal_messages WHERE id=%s AND thread_id=%s',(job['message_id'],thread['id'])).fetchone()['content']
            else:
                event=c.execute('SELECT event_type,reason FROM appeal_events WHERE thread_id=%s AND id=%s',(thread['id'],job['event_id'])).fetchone()
                body=event['event_type']+'\n'+event['reason']
            return {**thread,'body':body}

    def delivery_state(self, job, *, started=True, receipt=None):
        with transaction(self.database_url) as c:
            return c.execute('UPDATE appeal_outbox SET delivery_started=%s,discord_message_id=%s WHERE id=%s AND lease_owner=%s AND lease_token=%s AND lease_until>%s AND status=\'processing\'',
                (int(started),receipt,job['id'],job['_lease']['owner'],job['_lease']['token'],int(time.time()))).rowcount == 1

    def purge_expired(self, now=None):
        with transaction(self.database_url) as c:
            return c.execute('DELETE FROM appeal_threads WHERE id IN (SELECT id FROM appeal_threads WHERE expires_at<=%s ORDER BY expires_at LIMIT 500)',(int(time.time()) if now is None else now,)).rowcount

    def retry_delivery(self, guild, item_id, job_id, actor, *, revision):
        with transaction(self.database_url) as c:
            self._enabled(c,guild)
            row=self._item(c,guild,item_id,locked=True)
            if row['revision'] != revision:raise RuntimeError('revision_conflict')
            changed=c.execute("UPDATE appeal_outbox SET status='pending',attempts=0,available_at=%s,completed_at=NULL,last_error=NULL WHERE id=%s AND thread_id=%s AND status='failed' AND lease_owner IS NULL",(int(time.time()),job_id,item_id)).rowcount
            if not changed:raise RuntimeError('delivery_not_failed')
            self._event(c,item_id,actor,'delivery_retry',str(job_id),int(time.time()))
