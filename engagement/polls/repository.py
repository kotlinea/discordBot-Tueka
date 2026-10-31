"""Poll SQL, locking and atomic state changes. No external I/O."""
import json
import time
from database import require_current, transaction, lock_resource
from guild_settings import GuildSettingsRepository
from .models import PollError, normalize, selection, eligible, weight, preserve_privacy, permissions, disclose
from .publication.repository import PublicationRepository, PollQueue
from jobs.catalog import QUEUE_SPECS
UNSET = object()


class PollRepository(PublicationRepository):
    def __init__(self, url, *, clock=time.time):
        require_current(url)
        self.database_url, self.clock = url, clock
        self.settings = GuildSettingsRepository(url)
        self.jobs = PollQueue(url, QUEUE_SPECS['poll_outbox'], clock=clock)

    def _enabled(self, c, guild):
        lock_resource(c, 'guild-module', f'{guild}:advanced_polls')
        if not self.settings.get_module(guild, 'advanced_polls', _conn=c)['enabled']:
            raise PollError('disabled')

    def _access(self,c,guild,principal,permission):
        if principal is None:
            return
        lock_resource(c,'guild-module',f'{guild}:advanced_polls')
        settings=self.settings.get_module(guild,'advanced_polls',_conn=c)['settings']
        if principal.guild_id!=guild or permission not in permissions(principal,settings):
            raise PollError('forbidden')

    @staticmethod
    def _event(c, poll, actor, event, now):
        c.execute('INSERT INTO poll_events(poll_id,actor_id,event_type,created_at) VALUES(%s,%s,%s,%s)', (poll, actor, event, now))

    def _row(self, c, guild, poll, *, locked=False):
        row = c.execute('SELECT * FROM polls WHERE guild_id=%s AND id=%s' + (' FOR UPDATE' if locked else ''), (guild, poll)).fetchone()
        if not row:
            raise PollError('not_found')
        return dict(row)

    @staticmethod
    def _snapshot(c, row):
        data = dict(row)
        data['config'] = data.pop('config_json')
        data['options'] = data['config']['options']
        data['ballots'] = [dict(item) for item in c.execute('SELECT user_id,choices,weight FROM poll_ballots WHERE poll_id=%s ORDER BY user_id', (row['id'],)).fetchall()]
        data['counts'], data['weighted_counts'] = [0] * len(data['options']), [0] * len(data['options'])
        for ballot in data['ballots']:
            for index in ballot['choices']:
                data['counts'][index] += 1
                data['weighted_counts'][index] += ballot['weight']
        data['total'] = len(data['ballots'])
        return data

    def get(self, guild, poll):
        with transaction(self.database_url) as c:
            return self._snapshot(c, self._row(c, guild, poll, locked=True))

    def read(self,principal,poll,*,management=False):
        with transaction(self.database_url) as c:
            guild=principal.guild_id
            lock_resource(c,'guild-module',f'{guild}:advanced_polls')
            rights=permissions(principal,self.settings.get_module(guild,'advanced_polls',_conn=c)['settings'])
            if principal.bot or (management and 'view' not in rights):raise PollError('forbidden')
            snapshot=self._snapshot(c,self._row(c,guild,poll,locked=True))
            if 'view' not in rights and (snapshot['message_id'] is None or snapshot['status'] in ('draft','scheduled','publishing','cancelled','deleted')):
                raise PollError('not_found')
            result=disclose(snapshot,admin=bool(rights & {'manage','view_votes'}),view_votes='view_votes' in rights)
            if management and 'manage' in rights:result['config']=dict(snapshot['config'])
            return result

    def by_message(self, message):
        with transaction(self.database_url) as c:
            row = c.execute('SELECT * FROM polls WHERE message_id=%s FOR UPDATE', (message,)).fetchone()
            return self._snapshot(c, row) if row else None

    def items(self, guild, *, before=None, limit=50):
        with transaction(self.database_url) as c:
            rows = c.execute('SELECT * FROM polls WHERE guild_id=%s AND (%s::bigint IS NULL OR id<%s) ORDER BY id DESC LIMIT %s',
                             (guild, before, before, max(1, min(limit, 100)))).fetchall()
            return [self._snapshot(c, self._row(c, guild, row['id'], locked=True)) for row in rows]

    def create(self, guild, channel, actor, values, request_key, *, scheduled_at=None, duration_seconds=None, closes_at=None, principal=None):
        config = normalize(values)
        if not isinstance(request_key, str) or not 1 <= len(request_key) <= 100:
            raise PollError('invalid')
        fingerprint = dict(config=config, channel=channel, actor=actor, scheduled_at=scheduled_at, duration_seconds=duration_seconds, closes_at=closes_at)
        with transaction(self.database_url) as c:
            self._access(c,guild,principal,'manage')
            self._enabled(c, guild)
            lock_resource(c, 'poll-create', str(guild))
            old = c.execute('SELECT * FROM polls WHERE guild_id=%s AND request_key=%s FOR UPDATE', (guild, request_key)).fetchone()
            if old:
                if old['request_json'] != fingerprint:
                    raise PollError('conflict')
                return self._snapshot(c, old)
            now = int(self.clock())
            if scheduled_at is not None and (type(scheduled_at) is not int or not now < scheduled_at <= now + 365 * 86400):
                raise PollError('invalid')
            if duration_seconds is not None and (type(duration_seconds) is not int or not 1 <= duration_seconds <= 30 * 86400):
                raise PollError('invalid')
            if closes_at is not None and (type(closes_at) is not int or not (scheduled_at or now) < closes_at <= (scheduled_at or now) + 30 * 86400 or duration_seconds is not None):
                raise PollError('invalid')
            row = c.execute('''INSERT INTO polls(guild_id,channel_id,creator_id,question,options_json,image_url,closes_at,created_at,
                config_json,status,scheduled_at,duration_seconds,request_key) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *''',
                (guild, channel, actor, config['question'], json.dumps(config['options']), config['image_url'], closes_at, now,
                 json.dumps(config), 'scheduled' if scheduled_at else 'draft', scheduled_at, duration_seconds, request_key)).fetchone()
            self._event(c, row['id'], actor, 'created', now)
            c.execute('UPDATE polls SET request_json=%s,updated_at=%s WHERE id=%s',(json.dumps(fingerprint),now,row['id']))
            return self._snapshot(c, row)

    def vote(self, guild, poll, user, choices, *, revision, roles=(), bot=False, message_id=None):
        with transaction(self.database_url) as c:
            self._enabled(c, guild)
            weights = self.settings.get_module(guild, 'advanced_polls', _conn=c)['settings']['role_weights']
            row = self._row(c, guild, poll, locked=True)
            now = int(self.clock())
            if type(revision) is not int or row['revision']!=revision:
                raise PollError('conflict')
            if row['status'] != 'open' or (row['closes_at'] is not None and row['closes_at'] <= now):
                raise PollError('closed')
            if message_id is not None and row['message_id'] != message_id:
                raise PollError('not_found')
            config = row['config_json']
            if not eligible(config, user, roles, bot=bot):
                raise PollError('ineligible')
            selected = selection(choices, len(config['options']), config['max_choices'])
            if selected:
                c.execute('''INSERT INTO poll_ballots(poll_id,user_id,choices,weight,updated_at) VALUES(%s,%s,%s,%s,%s)
                    ON CONFLICT(poll_id,user_id) DO UPDATE SET choices=excluded.choices,weight=excluded.weight,updated_at=excluded.updated_at''',
                    (poll, user, json.dumps(selected), weight(weights or {}, roles), now))
                c.execute('UPDATE polls SET ever_voted=TRUE WHERE id=%s', (poll,))
            else:
                c.execute('DELETE FROM poll_ballots WHERE poll_id=%s AND user_id=%s', (poll, user))
            total = c.execute('SELECT count(*) AS n FROM poll_ballots WHERE poll_id=%s', (poll,)).fetchone()['n']
            close = config['max_participants'] is not None and total >= config['max_participants']
            row = c.execute('''UPDATE polls SET display_revision=display_revision+1,
                status=CASE WHEN %s THEN 'closed' ELSE status END,closed_at=CASE WHEN %s THEN %s ELSE closed_at END
                WHERE id=%s RETURNING *''', (close, close, now, poll)).fetchone()
            if close:
                self._event(c, poll, None, 'participant_limit', now)
                self._close_actions(c, row, now)
            return self._snapshot(c, row)

    def edit(self, guild, poll, actor, values, revision, *, closes_at=UNSET, scheduled_at=UNSET, duration_seconds=UNSET, principal=None):
        config = normalize(values)
        with transaction(self.database_url) as c:
            self._access(c,guild,principal,'manage')
            self._enabled(c, guild)
            row = self._row(c, guild, poll, locked=True)
            now = int(self.clock())
            if row['revision'] != revision or row['status'] in ('deleted', 'cancelled', 'publishing'):
                raise PollError('conflict')
            schedule=row['scheduled_at'] if scheduled_at is UNSET else scheduled_at
            period=row['duration_seconds'] if duration_seconds is UNSET else duration_seconds
            closes_at=row['closes_at'] if closes_at is UNSET else closes_at
            if (schedule,period)!=(row['scheduled_at'],row['duration_seconds']) and row['status'] not in ('draft','scheduled'):
                raise PollError('conflict')
            if row['status'] in ('draft','scheduled'):
                if schedule is not None and schedule!=row['scheduled_at'] and (type(schedule) is not int or not now<schedule<=now+365*86400):raise PollError('invalid')
                if period is not None and (type(period) is not int or not 1<=period<=30*86400):raise PollError('invalid')
                if period is not None and closes_at is not None:raise PollError('invalid')
            base=(schedule or now) if row['status'] in ('draft','scheduled') else now
            if closes_at is not None and closes_at!=row['closes_at'] and (type(closes_at) is not int or not base < closes_at <= base + 30 * 86400):
                raise PollError('invalid')
            if row['ever_voted']:
                mutable = {'color', 'image_url', 'max_participants', 'visibility', 'mode','button_style'}
                if any(config[key] != row['config_json'][key] for key in config.keys() - mutable):
                    raise PollError('ballot_locked')
                preserve_privacy(row['config_json']['visibility'], config['visibility'])
            row = c.execute('''UPDATE polls SET config_json=%s,question=%s,options_json=%s,image_url=%s,closes_at=%s,
                revision=revision+1,display_revision=display_revision+1,updated_at=%s,scheduled_at=%s,duration_seconds=%s,
                status=CASE WHEN status IN ('draft','scheduled') THEN %s ELSE status END WHERE id=%s RETURNING *''',
                (json.dumps(config), config['question'], json.dumps(config['options']), config['image_url'], closes_at, now, schedule,period,'scheduled' if schedule else 'draft',poll)).fetchone()
            self._event(c, poll, actor, 'edited', now)
            return self._snapshot(c, row)

    def transition(self, guild, poll, actor, action, revision, *, closes_at=None, principal=None):
        with transaction(self.database_url) as c:
            self._access(c,guild,principal,'manage')
            if action == 'reopen':
                self._enabled(c, guild)
            row = self._row(c, guild, poll, locked=True)
            now = int(self.clock())
            allowed = {'close': ('open',), 'reopen': ('closed',), 'delete': ('draft', 'scheduled', 'publishing', 'open', 'closed', 'cancelled'), 'cancel': ('draft', 'scheduled', 'publishing')}
            if row['revision'] != revision or action not in allowed or row['status'] not in allowed[action]:
                raise PollError('conflict')
            if action in ('cancel','delete'):
                jobs=c.execute("SELECT delivery_started,discord_receipt_id FROM poll_outbox WHERE poll_id=%s AND status NOT IN ('completed','cancelled') FOR UPDATE",(poll,)).fetchall()
                if any(job['delivery_started'] and job['discord_receipt_id'] is None for job in jobs):raise PollError('delivery_uncertain')
                c.execute("UPDATE poll_outbox SET status='cancelled',completed_at=%s,lease_owner=NULL,lease_token=NULL,lease_until=NULL WHERE poll_id=%s AND status NOT IN ('completed','cancelled')",(now,poll))
            if action == 'reopen':
                if closes_at is not None and (type(closes_at) is not int or not now < closes_at <= now + 30 * 86400):
                    raise PollError('invalid')
                total = c.execute('SELECT count(*) AS n FROM poll_ballots WHERE poll_id=%s', (poll,)).fetchone()['n']
                cap = row['config_json']['max_participants']
                if cap and total >= cap:
                    raise PollError('participant_limit')
            state = {'close': 'closed', 'reopen': 'open', 'delete': 'deleted', 'cancel': 'cancelled'}[action]
            row = c.execute('''UPDATE polls SET status=%s,revision=revision+1,display_revision=display_revision+1,
                closes_at=CASE WHEN %s THEN %s ELSE closes_at END,closed_at=%s WHERE id=%s RETURNING *''',
                (state, action == 'reopen', closes_at, None if action == 'reopen' else now, poll)).fetchone()
            if action == 'delete':
                c.execute('DELETE FROM poll_ballots WHERE poll_id=%s', (poll,))
                if row.get('thread_id'):self._enqueue(c,row,'archive',now)
            self._event(c, poll, actor, action, now)
            if action == 'close':
                self._close_actions(c, row, now)
            return self._snapshot(c, row)

    def close_expired(self):
        with transaction(self.database_url) as c:
            rows = c.execute("SELECT * FROM polls WHERE status IN ('open','scheduled') AND closes_at IS NOT NULL AND closes_at<=%s FOR UPDATE SKIP LOCKED", (int(self.clock()),)).fetchall()
            for row in rows:
                now = int(self.clock())
                c.execute("UPDATE polls SET status='closed',closed_at=%s,revision=revision+1,display_revision=display_revision+1 WHERE id=%s", (now, row['id']))
                self._event(c, row['id'], None, 'expired', now)
                closed = dict(row, status='closed', revision=row['revision']+1)
                self._close_actions(c, closed, now)
            return [dict(row) for row in rows]

    def pending_displays(self):
        with transaction(self.database_url) as c:
            return [row['message_id'] for row in c.execute("SELECT p.message_id FROM polls p LEFT JOIN guild_modules g ON g.guild_id=p.guild_id AND g.module_id='advanced_polls' WHERE p.message_id IS NOT NULL AND (p.display_revision<>p.synced_revision OR p.display_enabled IS DISTINCT FROM COALESCE(g.enabled=1,FALSE)) ORDER BY p.display_checked_at,p.id LIMIT 100").fetchall()]

    def display_attempted(self,message):
        with transaction(self.database_url) as c:
            c.execute('UPDATE polls SET display_checked_at=%s WHERE message_id=%s',(int(self.clock()),message))

    def ack_display(self, message, revision, enabled=None):
        with transaction(self.database_url) as c:
            row=c.execute('SELECT guild_id FROM polls WHERE message_id=%s',(message,)).fetchone()
            if not row:return
            lock_resource(c,'guild-module',f"{row['guild_id']}:advanced_polls")
            current=self.settings.get_module(row['guild_id'],'advanced_polls',_conn=c)['enabled']
            enabled=current if enabled is None else enabled
            c.execute('UPDATE polls SET synced_revision=CASE WHEN display_revision=%s AND %s THEN display_revision ELSE 0 END,display_enabled=%s WHERE message_id=%s', (revision,enabled==current,enabled,message))

    def history(self, guild, poll):
        with transaction(self.database_url) as c:
            self._row(c, guild, poll)
            return [dict(row) for row in c.execute('SELECT id,actor_id,event_type,created_at FROM poll_events WHERE poll_id=%s ORDER BY id DESC LIMIT 100', (poll,)).fetchall()]

    def remove_vote(self, guild, poll, actor, user, revision, *, principal=None):
        with transaction(self.database_url) as c:
            self._access(c,guild,principal,'manage_votes')
            row = self._row(c, guild, poll, locked=True)
            if row['revision'] != revision or row['status'] in ('deleted','cancelled'):
                raise PollError('conflict')
            c.execute('DELETE FROM poll_ballots WHERE poll_id=%s AND user_id=%s', (poll,user))
            c.execute('UPDATE polls SET revision=revision+1,display_revision=display_revision+1 WHERE id=%s', (poll,))
            # Target voter is deliberately excluded from audit, including anonymous polls.
            self._event(c, poll, actor, 'vote_removed', int(self.clock()))

    def remove_departed(self, guild, user):
        with transaction(self.database_url) as c:
            rows = c.execute("SELECT id FROM polls WHERE guild_id=%s AND status IN ('open','closed') AND config_json->>'remove_departed_votes'='true' ORDER BY id FOR UPDATE", (guild,)).fetchall()
            for row in rows:
                if c.execute('DELETE FROM poll_ballots WHERE poll_id=%s AND user_id=%s', (row['id'],user)).rowcount:
                    c.execute('UPDATE polls SET display_revision=display_revision+1 WHERE id=%s', (row['id'],))

    def departure_candidates(self,after=(0,0)):
        with transaction(self.database_url) as c:
            return [dict(row) for row in c.execute("SELECT DISTINCT p.guild_id,b.user_id FROM polls p JOIN poll_ballots b ON b.poll_id=p.id WHERE p.status IN ('open','closed') AND p.config_json->>'remove_departed_votes'='true' AND (p.guild_id,b.user_id)>(%s,%s) ORDER BY p.guild_id,b.user_id LIMIT 10",after).fetchall()]

    def save_settings(self, principal, values, revision, *, enabled=None):
        from guild_settings.engagement.advanced_polls import normalize as normalize_settings
        with transaction(self.database_url) as c:
            guild=principal.guild_id
            lock_resource(c,'guild-module',f'{guild}:advanced_polls')
            old=self.settings.get_module(guild,'advanced_polls',_conn=c)
            if old['revision']!=revision:raise PollError('conflict')
            if not permissions(principal,old['settings']) & {'settings','weights','permissions'}:raise PollError('forbidden')
            new=normalize_settings({**old['settings'],**values})
            enabled=old['enabled'] if enabled is None else enabled
            if enabled!=old['enabled']:self._access(c,guild,principal,'settings')
            for key,permission in (('retention_days','settings'),('role_weights','weights'),('role_permissions','permissions')):
                if new[key]!=old['settings'][key]:
                    self._access(c,guild,principal,permission)
                    c.execute('INSERT INTO poll_setting_events(guild_id,actor_id,event_type,created_at) VALUES(%s,%s,%s,%s)',(guild,principal.user_id,permission+'_changed',int(self.clock())))
            if enabled!=old['enabled']:
                c.execute('INSERT INTO poll_setting_events(guild_id,actor_id,event_type,created_at) VALUES(%s,%s,%s,%s)',(guild,principal.user_id,'enabled_changed',int(self.clock())))
            return self.settings.set_module(guild,'advanced_polls',enabled=enabled,settings=new,expected_revision=revision,_conn=c)

    def settings_history(self,guild):
        with transaction(self.database_url) as c:
            return [dict(row) for row in c.execute('SELECT id,actor_id,event_type,created_at FROM poll_setting_events WHERE guild_id=%s ORDER BY id DESC LIMIT 100',(guild,)).fetchall()]

    def purge_expired(self):
        now = int(self.clock())
        with transaction(self.database_url) as c:
            c.execute("DELETE FROM poll_setting_events e WHERE created_at<%s-COALESCE((SELECT (g.settings_json::jsonb->>'retention_days')::int FROM guild_modules g WHERE g.guild_id=e.guild_id AND g.module_id='advanced_polls'),90)*86400",(now,))
            return c.execute('''DELETE FROM polls WHERE id IN (SELECT p.id FROM polls p
                LEFT JOIN guild_modules g ON g.guild_id=p.guild_id AND g.module_id='advanced_polls'
                WHERE ((p.status='draft' AND p.updated_at<%s) OR (p.closed_at IS NOT NULL AND p.closed_at<%s-COALESCE((g.settings_json::jsonb->>'retention_days')::int,90)*86400))
                AND NOT EXISTS(SELECT 1 FROM poll_outbox j WHERE j.poll_id=p.id AND ((j.delivery_started=1 AND j.discord_receipt_id IS NULL) OR j.lease_until>%s))
                ORDER BY p.id LIMIT 500)''', (now-7*86400,now,now)).rowcount
