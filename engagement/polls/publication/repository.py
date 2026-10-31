"""Poll publication SQL, queue ownership and uncertain send boundaries."""
from database import transaction
from jobs import QueueRepository, LostLease
from jobs.catalog import QUEUE_SPECS
from ..models import PollError


class PollQueue(QueueRepository):
    def _claim_scope(self):
        return (" AND (action='stop_old' OR EXISTS(SELECT 1 FROM guild_modules g WHERE g.guild_id=poll_outbox.guild_id AND g.module_id='advanced_polls' AND g.enabled=1))", ())

    def purge(self, **_):
        return 0


class PublicationRepository:
    """Mixed into PollRepository; owns only its publication transaction helpers."""

    def _enqueue(self, c, row, action, now, *, channel=None):
        c.execute('''INSERT INTO poll_outbox(poll_id,guild_id,action,channel_id,generation,available_at,created_at,old_message_id,old_channel_id)
            VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(poll_id,action,generation) DO NOTHING''',
            (row['id'], row['guild_id'], action, channel or row['channel_id'], row['revision'], now, now, row['message_id'], row['channel_id']))

    def _close_actions(self, c, row, now):
        if row['message_id'] is None:
            return
        config = row['config_json']
        for setting,action in (('announce_winner','announce'),('pin_on_close','pin')):
            if config.get(setting) and (action != 'announce' or config['visibility']['closed']['counts']=='everyone'):
                self._enqueue(c,row,action,now)
        if row.get('thread_id'):
            self._enqueue(c,row,'archive',now)

    def launch(self, guild, poll, actor, revision, *, channel=None, principal=None):
        with transaction(self.database_url) as c:
            self._access(c,guild,principal,'manage')
            self._enabled(c, guild)
            row = self._row(c, guild, poll, locked=True)
            if row['revision'] != revision or row['status'] not in ('draft', 'scheduled', 'open', 'closed'):
                raise PollError('conflict')
            if row['scheduled_at'] and row['scheduled_at'] > int(self.clock()):
                raise PollError('not_due')
            if c.execute("SELECT 1 FROM poll_outbox WHERE poll_id=%s AND status NOT IN ('completed','cancelled')", (poll,)).fetchone():
                raise PollError('delivery_uncertain')
            action = 'move' if row['message_id'] is not None else 'publish'
            if action == 'move' and not channel:
                raise PollError('invalid')
            row = c.execute('''UPDATE polls SET revision=revision+1,updated_at=%s,
                status=CASE WHEN message_id IS NULL THEN 'publishing' ELSE status END WHERE id=%s RETURNING *''', (int(self.clock()), poll)).fetchone()
            self._enqueue(c, row, action, int(self.clock()), channel=channel)
            self._event(c, poll, actor, 'publication_requested' if action == 'publish' else 'move_requested', int(self.clock()))
            return self._snapshot(c, row)

    def _owned(self, c, job):
        row = c.execute("SELECT * FROM poll_outbox WHERE id=%s AND status='processing' AND lease_owner=%s AND lease_token=%s FOR UPDATE",
                        (job['id'], job['_lease']['owner'], job['_lease']['token'])).fetchone()
        if not row or row['lease_until'] is None or row['lease_until'] <= int(self.clock()):
            raise LostLease('Poll delivery ownership expired')
        return row

    def start_delivery(self, job):
        with transaction(self.database_url) as c:
            # Module -> poll -> job everywhere avoids a cycle with edits/cancellation.
            enabled = True
            if job['action'] != 'stop_old':
                try:
                    self._enabled(c, job['guild_id'])
                except PollError:
                    enabled = False
            row = self._row(c, job['guild_id'], job['poll_id'], locked=True)
            owned = self._owned(c, job)
            snapshot = self._snapshot(c, row)
            if owned['discord_receipt_id'] is not None:
                return 'done', snapshot
            # A previous send always reconciles, even if state changed since then.
            if owned['delivery_started']:
                return 'recover', snapshot
            if not enabled:
                return 'paused', snapshot
            if job['action'] in ('publish', 'move') and (row['revision'] != job['generation'] or row['status'] in ('deleted', 'cancelled')):
                return 'done', snapshot
            if job['action'] in ('announce','pin','archive'):
                config=row['config_json']
                if job['action']=='announce' and (row['status']!='closed' or not config.get('announce_winner') or config['visibility']['closed']['counts']!='everyone'):
                    return 'done', snapshot
                if job['action']=='pin' and (row['status']!='closed' or not config.get('pin_on_close')):
                    return 'done', snapshot
                if job['action']=='archive' and (row['status'] not in ('closed','deleted') or not row.get('thread_id')):
                    return 'done', snapshot
                # A later closing cycle supersedes this intent; cosmetic edits do not.
                if c.execute('SELECT 1 FROM poll_outbox WHERE poll_id=%s AND action=%s AND generation>%s LIMIT 1',
                             (row['id'],job['action'],job['generation'])).fetchone():
                    return 'done', snapshot
            if job['action']=='thread' and row['status'] in ('deleted','cancelled'):
                return 'done', snapshot
            if job['action'] == 'publish' and row['closes_at'] is not None and row['closes_at'] <= int(self.clock()):
                c.execute("UPDATE polls SET status='closed',closed_at=%s,revision=revision+1 WHERE id=%s", (int(self.clock()), row['id']))
                self._event(c,row['id'],None,'expired_before_publication',int(self.clock()))
                return 'done', snapshot
            c.execute('UPDATE poll_outbox SET delivery_started=1 WHERE id=%s', (job['id'],))
            return 'send', snapshot

    def reset_delivery(self, job):
        with transaction(self.database_url) as c:
            self._owned(c, job)
            c.execute('UPDATE poll_outbox SET delivery_started=0 WHERE id=%s', (job['id'],))

    def receipt(self, job, message):
        with transaction(self.database_url) as c:
            row = self._row(c, job['guild_id'], job['poll_id'], locked=True)
            self._owned(c, job)
            now = int(self.clock())
            c.execute('UPDATE poll_outbox SET discord_receipt_id=%s WHERE id=%s', (message, job['id']))
            if job['action'] in ('publish', 'move'):
                # Cancellation while sending cannot discard the receipt or reactivate voting.
                state = 'open' if row['status'] == 'publishing' else row['status']
                deadline = now + row['duration_seconds'] if row['duration_seconds'] and row['published_at'] is None else row['closes_at']
                if deadline is not None and deadline <= now and state == 'open':
                    state = 'closed'
                c.execute('''UPDATE polls SET message_id=%s,channel_id=%s,published_at=COALESCE(published_at,%s),closes_at=%s,
                    status=%s,closed_at=CASE WHEN %s='closed' THEN COALESCE(closed_at,%s) ELSE closed_at END,
                    display_revision=display_revision+1 WHERE id=%s''', (message, job['channel_id'], now, deadline, state,state,now,row['id']))
                if job['old_message_id']:
                    self._enqueue(c, row, 'stop_old', now)
                current = self._row(c, row['guild_id'], row['id'])
                if state=='closed' and row['closed_at'] is None:
                    self._event(c,row['id'],None,'expired_during_publication',now)
                    self._close_actions(c,current,now)
                if current['config_json'].get('create_thread') and current['thread_id'] is None:
                    self._enqueue(c,current,'thread',now)
                self._event(c, row['id'], None, 'published' if job['action'] == 'publish' else 'moved', now)
            elif job['action']=='thread':
                c.execute('UPDATE polls SET thread_id=%s WHERE id=%s',(message,row['id']))
                if row['status']!='open':
                    self._enqueue(c,dict(row,thread_id=message),'archive',now)
            return True

    def retry_delivery(self, guild, poll, job, actor, revision, *, principal=None):
        with transaction(self.database_url) as c:
            self._access(c,guild,principal,'manage')
            self._enabled(c,guild)
            row=self._row(c,guild,poll,locked=True)
            if row['revision']!=revision:raise PollError('conflict')
            changed=c.execute("UPDATE poll_outbox SET status='pending',attempts=0,available_at=%s,completed_at=NULL,last_error=NULL WHERE id=%s AND poll_id=%s AND status='failed' AND lease_owner IS NULL",(int(self.clock()),job,poll)).rowcount
            if changed!=1:raise PollError('conflict')
            self._event(c,poll,actor,'delivery_retry',int(self.clock()))

    def enqueue_due(self):
        with transaction(self.database_url) as c:
            rows = c.execute("SELECT p.guild_id,p.id,p.revision FROM polls p JOIN guild_modules g ON g.guild_id=p.guild_id AND g.module_id='advanced_polls' AND g.enabled=1 WHERE p.status='scheduled' AND p.scheduled_at<=%s ORDER BY p.scheduled_at LIMIT 50", (int(self.clock()),)).fetchall()
        for row in rows:
            try:
                self.launch(row['guild_id'], row['id'], None, row['revision'])
            except PollError:
                continue

    def delivery_history(self, guild, poll):
        with transaction(self.database_url) as c:
            self._row(c, guild, poll)
            return [dict(row) for row in c.execute('SELECT id,action,status,attempts,last_error,discord_receipt_id FROM poll_outbox WHERE poll_id=%s ORDER BY id DESC LIMIT 100', (poll,)).fetchall()]
