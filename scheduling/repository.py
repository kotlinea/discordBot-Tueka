"""Transactional schedules, occurrence snapshots, cancellation and receipt fencing."""
import json
import time
from database import require_current, transaction, lock_resource
from guild_settings import GuildSettingsRepository
from jobs import QueueRepository, LostLease
from jobs.catalog import QUEUE_SPECS
from .service import normalize, short


class ScheduleQueue(QueueRepository):
    def _claim_scope(self):
        return (' AND EXISTS(SELECT 1 FROM guild_modules g WHERE g.guild_id=scheduled_post_outbox.guild_id'
                ' AND g.module_id=%s AND g.enabled=1)', ('scheduled_messages',))

    def purge(self, **_):
        # Parent schedules own the configured retention and cascading cleanup.
        return 0


class ScheduleRepository:
    def __init__(self, url, *, clock=time.time):
        require_current(url)
        self.database_url, self.clock = url, clock
        self.settings = GuildSettingsRepository(url)
        self.jobs = ScheduleQueue(url, QUEUE_SPECS['scheduled_post_outbox'], clock=clock)

    def _enabled(self, c, guild):
        lock_resource(c, 'guild-module', f'{guild}:scheduled_messages')
        module = self.settings.get_module(guild, 'scheduled_messages', _conn=c)
        if not module['enabled']:
            raise PermissionError('scheduling_disabled')
        return module['settings']

    def _item(self, c, guild, item, *, locked=False):
        row = c.execute('SELECT * FROM scheduled_posts WHERE guild_id=%s AND id=%s AND expires_at>%s' + (' FOR UPDATE' if locked else ''), (guild,item,int(self.clock()))).fetchone()
        if not row:
            raise LookupError('schedule_not_found')
        return row

    @staticmethod
    def _event(c, item, actor, event, now, detail=''):
        c.execute('INSERT INTO scheduled_post_events(post_id,actor_id,event_type,detail,created_at) VALUES(%s,%s,%s,%s,%s)', (item,actor,event,detail,now))

    def create(self, guild, actor, values, request_key):
        now = int(self.clock())
        request_key = short(request_key, 'request_key', 100, required=True)
        with transaction(self.database_url) as c:
            settings = self._enabled(c,guild)
            lock_resource(c,'scheduled-create',str(guild))
            old = c.execute('SELECT * FROM scheduled_posts WHERE guild_id=%s AND request_key=%s', (guild,request_key)).fetchone()
            if old:
                if old['expires_at'] <= now:
                    raise LookupError('schedule_expired')
                payload = normalize(values,old['created_at'])
                if old['actor_id'] != actor or json.loads(old['payload_json']) != payload:
                    raise RuntimeError('request_key_conflict')
                return old
            payload = normalize(values,now)
            active = c.execute("SELECT count(*) AS n FROM scheduled_posts WHERE guild_id=%s AND status='scheduled'", (guild,)).fetchone()['n']
            if active >= 100:
                raise ValueError('schedule_limit')
            expiry = payload['run_at'] + payload['interval_seconds'] * (payload['occurrences']-1) + settings['retention_days']*86400
            row = c.execute('INSERT INTO scheduled_posts(guild_id,actor_id,request_key,payload_json,next_due,interval_seconds,remaining,retention_days,created_at,updated_at,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *',
                (guild,actor,request_key,json.dumps(payload),payload['run_at'],payload['interval_seconds'],payload['occurrences'],settings['retention_days'],now,now,expiry)).fetchone()
            self._event(c,row['id'],actor,'created',now)
            return row

    def item(self, guild, item):
        with transaction(self.database_url) as c:
            return self._item(c,guild,item)

    def items(self, guild, *, before=None, limit=50):
        with transaction(self.database_url) as c:
            return c.execute('SELECT * FROM scheduled_posts WHERE guild_id=%s AND expires_at>%s AND (%s::bigint IS NULL OR id<%s) ORDER BY id DESC LIMIT %s', (guild,int(self.clock()),before,before,max(1,min(limit,100)))).fetchall()

    def history(self, guild, item):
        with transaction(self.database_url) as c:
            self._item(c,guild,item)
            return dict(events=c.execute('SELECT * FROM scheduled_post_events WHERE post_id=%s ORDER BY id DESC LIMIT 100',(item,)).fetchall(),
                        delivery=c.execute('SELECT id,due_at,deadline,status,attempts,delivery_started,discord_receipt_id FROM scheduled_post_outbox WHERE post_id=%s ORDER BY id DESC LIMIT 100',(item,)).fetchall())

    def cancel(self, guild, item, actor, revision):
        now = int(self.clock())
        with transaction(self.database_url) as c:
            self._enabled(c,guild)
            row = self._item(c,guild,item,locked=True)
            if row['revision'] != revision or row['status'] == 'cancelled':
                raise RuntimeError('revision_or_status_conflict')
            # Keep start/receipt uncertainty until reconciliation; never promise cancellation mid-send.
            if c.execute('SELECT 1 FROM scheduled_post_outbox WHERE post_id=%s AND delivery_started=1 AND discord_receipt_id IS NULL',(item,)).fetchone():
                raise RuntimeError('delivery_in_progress_or_uncertain')
            c.execute("UPDATE scheduled_post_outbox SET status='cancelled',completed_at=%s,lease_owner=NULL,lease_token=NULL,lease_until=NULL WHERE post_id=%s AND status IN ('pending','retry','processing','failed')",(now,item))
            row = c.execute("UPDATE scheduled_posts SET status='cancelled',remaining=0,revision=revision+1,updated_at=%s,expires_at=%s WHERE id=%s RETURNING *",(now,now+row['retention_days']*86400,item)).fetchone()
            self._event(c,item,actor,'cancelled',now)
            return row

    def reschedule(self, guild, item, actor, values, revision):
        now = int(self.clock())
        payload = normalize(values,now)
        with transaction(self.database_url) as c:
            self._enabled(c,guild)
            row = self._item(c,guild,item,locked=True)
            if row['revision'] != revision or row['status'] != 'scheduled':
                raise RuntimeError('revision_or_status_conflict')
            if c.execute('SELECT 1 FROM scheduled_post_outbox WHERE post_id=%s LIMIT 1',(item,)).fetchone():
                raise RuntimeError('occurrence_already_reserved')
            expiry = payload['run_at']+payload['interval_seconds']*(payload['occurrences']-1)+row['retention_days']*86400
            row = c.execute('UPDATE scheduled_posts SET payload_json=%s,next_due=%s,interval_seconds=%s,remaining=%s,revision=revision+1,updated_at=%s,expires_at=%s WHERE id=%s RETURNING *', (json.dumps(payload),payload['run_at'],payload['interval_seconds'],payload['occurrences'],now,expiry,item)).fetchone()
            self._event(c,item,actor,'rescheduled',now)
            return row

    def enqueue_due(self, *, limit=50):
        """At most one on-time occurrence per schedule; skip old slots arithmetically."""
        now, count = int(self.clock()), 0
        enabled = self.settings.enabled_module_guild_ids('scheduled_messages')
        if not enabled:
            return 0
        with transaction(self.database_url) as c:
            # Lock modules before rows, matching API/cancellation lock order.
            guilds = c.execute("SELECT DISTINCT guild_id FROM scheduled_posts WHERE status='scheduled' AND next_due<=%s AND guild_id=ANY(%s) ORDER BY guild_id LIMIT %s",(now,enabled,max(1,min(limit,100)))).fetchall()
        for guild in guilds:
            with transaction(self.database_url) as c:
                try:
                    self._enabled(c,guild['guild_id'])
                except PermissionError:
                    continue
                rows = c.execute("SELECT * FROM scheduled_posts WHERE guild_id=%s AND status='scheduled' AND next_due<=%s ORDER BY next_due,id LIMIT %s FOR UPDATE SKIP LOCKED",(guild['guild_id'],now,max(1,min(limit-count,100)))).fetchall()
                for row in rows:
                    due, remaining, interval = row['next_due'], row['remaining'], row['interval_seconds']
                    missed = min(remaining, max(0,(now-due-600+interval-1)//interval)) if interval else int(now>due+600)
                    if missed:
                        remaining -= missed
                        due += missed*interval
                        self._event(c,row['id'],0,'missed',now,str(missed))
                    if remaining and due <= now:
                        c.execute('INSERT INTO scheduled_post_outbox(post_id,guild_id,due_at,deadline,payload_json,available_at,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(post_id,due_at) DO NOTHING', (row['id'],row['guild_id'],due,due+600,row['payload_json'],now,now))
                        remaining -= 1
                        due += interval
                        self._event(c,row['id'],0,'reserved',now)
                    next_due = due if remaining else due-interval
                    c.execute("UPDATE scheduled_posts SET next_due=%s,remaining=%s,status=%s,revision=revision+1,updated_at=%s WHERE id=%s",(next_due,remaining,'scheduled' if remaining else 'completed',now,row['id']))
                    count += 1
            if count >= limit:
                break
        return count

    def start_delivery(self, job):
        """Fence cancellation and module OFF against the irreversible start boundary."""
        now = int(self.clock())
        with transaction(self.database_url) as c:
            self._enabled(c,job['guild_id'])
            row = self._item(c,job['guild_id'],job['post_id'],locked=True)
            if row['status'] == 'cancelled':
                raise PermissionError('schedule_cancelled')
            owned = c.execute("SELECT * FROM scheduled_post_outbox WHERE id=%s AND status='processing' AND lease_owner=%s AND lease_token=%s AND lease_until>%s FOR UPDATE",(job['id'],job['_lease']['owner'],job['_lease']['token'],now)).fetchone()
            if not owned:
                raise LostLease('Scheduled delivery lease lost')
            if owned['discord_receipt_id']:
                return 'done'
            if not owned['delivery_started'] and now > owned['deadline']:
                return 'missed'
            c.execute('UPDATE scheduled_post_outbox SET delivery_started=1 WHERE id=%s',(job['id'],))
            return 'recover' if owned['delivery_started'] else 'send'

    def delivery_state(self, job, *, started=True, receipt=None):
        with transaction(self.database_url) as c:
            return c.execute("UPDATE scheduled_post_outbox SET delivery_started=%s,discord_receipt_id=%s WHERE id=%s AND status='processing' AND lease_owner=%s AND lease_token=%s AND lease_until>%s",(int(started),receipt,job['id'],job['_lease']['owner'],job['_lease']['token'],int(self.clock()))).rowcount == 1

    def retry(self, guild, item, job_id, actor, revision):
        now = int(self.clock())
        with transaction(self.database_url) as c:
            self._enabled(c,guild)
            row = self._item(c,guild,item,locked=True)
            if row['revision'] != revision or row['status'] == 'cancelled':
                raise RuntimeError('revision_or_status_conflict')
            # Expired attempts may only reconcile a potentially delivered receipt.
            changed = c.execute("UPDATE scheduled_post_outbox SET status='pending',attempts=0,available_at=%s,completed_at=NULL,last_error=NULL WHERE id=%s AND post_id=%s AND status='failed' AND lease_owner IS NULL AND (deadline>=%s OR delivery_started=1)",(now,job_id,item,now)).rowcount
            if changed != 1:
                raise RuntimeError('delivery_not_retryable')
            self._event(c,item,actor,'delivery_retry',now,str(job_id))

    def purge_expired(self):
        now = int(self.clock())
        with transaction(self.database_url) as c:
            return c.execute('DELETE FROM scheduled_posts WHERE id IN (SELECT p.id FROM scheduled_posts p WHERE p.expires_at<=%s AND NOT EXISTS(SELECT 1 FROM scheduled_post_outbox j WHERE j.post_id=p.id AND j.lease_until>%s) ORDER BY p.expires_at LIMIT 500)',(now,now)).rowcount
