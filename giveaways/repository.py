"""Campaign transactions, entry fencing, immutable draws and receipt ownership."""
import json
import time
from database import require_current, transaction, lock_resource
from guild_settings import GuildSettingsRepository
from jobs import QueueRepository, LostLease
from jobs.catalog import QUEUE_SPECS
from .models import normalize, text, snowflake, selection


class CampaignQueue(QueueRepository):
    def _claim_scope(self):
        if self.spec.table not in ('giveaway_outbox', 'giveaway_draw_jobs'):
            raise ValueError('Unsupported campaign queue')
        return (f' AND EXISTS(SELECT 1 FROM giveaways p JOIN guild_modules g ON g.guild_id=p.guild_id '
                f"AND g.module_id='giveaways' AND g.enabled=1 WHERE p.id={self.spec.table}.campaign_id)", ())

    def purge(self, **_):
        return 0  # Campaign retention owns all dependent records.


class GiveawayRepository:
    def __init__(self, url, *, clock=time.time):
        require_current(url)
        self.database_url, self.clock = url, clock
        self.settings = GuildSettingsRepository(url)
        self.jobs = CampaignQueue(url, QUEUE_SPECS['giveaway_outbox'], clock=clock)
        self.draw_jobs = CampaignQueue(url, QUEUE_SPECS['giveaway_draw_jobs'], clock=clock)

    def _enabled(self, c, guild):
        lock_resource(c, 'guild-module', f'{guild}:giveaways')
        if not self.settings.get_module(guild, 'giveaways', _conn=c)['enabled']:
            raise PermissionError('giveaways_disabled')

    def _item(self, c, guild, item, *, locked=False):
        row = c.execute('SELECT * FROM giveaways WHERE guild_id=%s AND id=%s AND expires_at>%s' +
                        (' FOR UPDATE' if locked else ''), (guild, item, int(self.clock()))).fetchone()
        if not row:
            raise LookupError('campaign_not_found')
        return {**row, 'config': json.loads(row['config_json'])}

    @staticmethod
    def _revision(row, revision):
        if type(revision) is not int or revision != row['revision']:
            raise RuntimeError('revision_conflict')

    @staticmethod
    def _audit(c, item, actor, event, now, detail=None):
        c.execute('INSERT INTO giveaway_events(campaign_id,actor_id,event_type,detail_json,created_at) VALUES(%s,%s,%s,%s,%s)',
                  (item, actor, event, json.dumps(detail or {}), now))

    @staticmethod
    def _queue(c, item, now, *, except_job=None):
        # Revision reconciliation precedes queue completion, so processing work
        # cannot replace a durable successor for a newly committed change.
        if not c.execute("SELECT 1 FROM giveaway_outbox WHERE campaign_id=%s AND status IN ('pending','retry') AND (%s::bigint IS NULL OR id<>%s)",
                         (item, except_job, except_job)).fetchone():
            c.execute('INSERT INTO giveaway_outbox(campaign_id,available_at,created_at) VALUES(%s,%s,%s)', (item, now, now))

    def _existing_creation(self, c, guild, actor, values, request_key, now):
        old = c.execute('SELECT * FROM giveaways WHERE guild_id=%s AND request_key=%s', (guild, request_key)).fetchone()
        if not old:
            return None
        if old['expires_at'] <= now:
            raise LookupError('campaign_expired')
        if old['actor_id'] != actor or json.loads(old['config_json']) != normalize(values, old['created_at']):
            raise RuntimeError('request_key_conflict')
        return self._item(c, guild, old['id'])

    def existing_creation(self, guild, actor, values, request_key):
        with transaction(self.database_url) as c:
            self._enabled(c, guild)
            return self._existing_creation(c, guild, actor, values, request_key, int(self.clock()))

    def create(self, guild, actor, values, request_key):
        now = int(self.clock())
        request_key = text(request_key, 'request_key', 100)
        with transaction(self.database_url) as c:
            self._enabled(c, guild)
            lock_resource(c, 'giveaway-create', str(guild))
            old = self._existing_creation(c, guild, actor, values, request_key, now)
            if old:
                return old
            config = normalize(values, now)
            if c.execute('SELECT count(*) AS n FROM giveaways WHERE guild_id=%s AND expires_at>%s', (guild, now)).fetchone()['n'] >= 100:
                raise ValueError('campaign_limit')
            row = c.execute('INSERT INTO giveaways(guild_id,actor_id,request_key,config_json,ends_at,created_at,updated_at,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *',
                            (guild, actor, request_key, json.dumps(config), config['ends_at'], now, now, config['ends_at'] + config['retention_days'] * 86400)).fetchone()
            self._audit(c, row['id'], actor, 'created', now)
            return self._item(c, guild, row['id'])

    def item(self, guild, item):
        with transaction(self.database_url) as c:
            return self._item(c, guild, item)

    def items(self, guild, *, before=None, limit=50):
        with transaction(self.database_url) as c:
            rows = c.execute('SELECT * FROM giveaways WHERE guild_id=%s AND expires_at>%s AND (%s::bigint IS NULL OR id<%s) ORDER BY id DESC LIMIT %s',
                            (guild, int(self.clock()), before, before, max(1, min(100, limit)))).fetchall()
            return [{**row, 'config': json.loads(row['config_json'])} for row in rows]

    def edit(self, guild, item, actor, values, revision):
        now = int(self.clock())
        with transaction(self.database_url) as c:
            self._enabled(c, guild)
            row = self._item(c, guild, item, locked=True)
            self._revision(row, revision)
            if row['status'] != 'draft':
                raise RuntimeError('campaign_already_launched')
            config = normalize(values, now)
            c.execute('UPDATE giveaways SET config_json=%s,ends_at=%s,expires_at=%s,revision=revision+1,updated_at=%s WHERE id=%s',
                      (json.dumps(config), config['ends_at'], config['ends_at'] + config['retention_days'] * 86400, now, item))
            self._audit(c, item, actor, 'edited', now)
            return self._item(c, guild, item)

    def launch(self, guild, item, actor, revision):
        now = int(self.clock())
        with transaction(self.database_url) as c:
            self._enabled(c, guild)
            row = self._item(c, guild, item, locked=True)
            self._revision(row, revision)
            if row['status'] != 'draft' or row['ends_at'] <= now:
                raise RuntimeError('campaign_not_launchable')
            c.execute("UPDATE giveaways SET status='open',revision=revision+1,updated_at=%s WHERE id=%s", (now, item))
            c.execute('INSERT INTO giveaway_draw_jobs(campaign_id,round_number,actor_id,reason,available_at,created_at) VALUES(%s,1,%s,%s,%s,%s)',
                      (item, actor, 'deadline', row['ends_at'], now))
            self._queue(c, item, now)
            self._audit(c, item, actor, 'launched', now)
            return self._item(c, guild, item)

    def enter(self, guild, item, user, message, interaction, *, join):
        now = int(self.clock())
        if type(join) is not bool:
            raise ValueError('invalid_participation_action')
        user = snowflake(user, 'user_id')
        interaction = snowflake(interaction, 'interaction_id')
        action = 'join' if join else 'leave'
        with transaction(self.database_url) as c:
            self._enabled(c, guild)
            row = self._item(c, guild, item, locked=True)
            old = c.execute('SELECT * FROM giveaway_interactions WHERE interaction_id=%s', (interaction,)).fetchone()
            if old:
                if (old['campaign_id'], old['user_id'], old['action']) != (item, user, action):
                    raise RuntimeError('interaction_conflict')
                return False
            if row['status'] != 'open' or row['ends_at'] <= now or row['message_id'] is None or row['message_id'] != message:
                raise RuntimeError('campaign_not_accepting')
            old_entry = c.execute('SELECT * FROM giveaway_entries WHERE campaign_id=%s AND user_id=%s', (item, user)).fetchone()
            if join and not old_entry and c.execute('SELECT count(*) AS n FROM giveaway_entries WHERE campaign_id=%s', (item,)).fetchone()['n'] >= 1000:
                raise ValueError('participant_history_limit')
            if c.execute('SELECT count(*) AS n FROM giveaway_interactions WHERE campaign_id=%s', (item,)).fetchone()['n'] >= 10000:
                raise ValueError('interaction_history_limit')
            if join and not (old_entry and old_entry['active']):
                if c.execute('SELECT count(*) AS n FROM giveaway_entries WHERE campaign_id=%s AND active=1', (item,)).fetchone()['n'] >= row['config']['capacity']:
                    raise ValueError('campaign_full')
            changed = not old_entry or bool(old_entry['active']) != join
            c.execute('INSERT INTO giveaway_interactions(interaction_id,campaign_id,user_id,action,created_at) VALUES(%s,%s,%s,%s,%s)',
                      (interaction, item, user, action, now))
            if not changed:
                return False
            # Leaving an entry that never existed does not create a participant.
            if old_entry or join:
                c.execute('INSERT INTO giveaway_entries(campaign_id,user_id,active,joined_at,updated_at) VALUES(%s,%s,%s,%s,%s) ON CONFLICT(campaign_id,user_id) DO UPDATE SET active=excluded.active,updated_at=excluded.updated_at',
                          (item, user, int(join), now, now))
                self._audit(c, item, user, action, now)
                c.execute('UPDATE giveaways SET revision=revision+1,updated_at=%s WHERE id=%s', (now, item))
                self._queue(c, item, now)
            return bool(old_entry or join)

    def cancel(self, guild, item, actor, revision, reason):
        reason = text(reason, 'reason', 500)
        now = int(self.clock())
        with transaction(self.database_url) as c:
            self._enabled(c, guild)
            row = self._item(c, guild, item, locked=True)
            self._revision(row, revision)
            if row['status'] in ('closed', 'cancelled'):
                raise RuntimeError('campaign_terminal')
            c.execute("UPDATE giveaways SET status='cancelled',revision=revision+1,updated_at=%s,expires_at=%s WHERE id=%s",
                      (now, now + row['config']['retention_days'] * 86400, item))
            c.execute("UPDATE giveaway_draw_jobs SET status='failed',last_error='Campaign cancelled',completed_at=%s,lease_owner=NULL,lease_token=NULL,lease_until=NULL WHERE campaign_id=%s AND status IN ('pending','retry','processing')", (now, item))
            if row['status'] != 'draft':
                self._queue(c, item, now)
            self._audit(c, item, actor, 'cancelled', now, {'reason': reason})
            return self._item(c, guild, item)

    def reroll(self, guild, item, actor, revision, reason):
        reason = text(reason, 'reason', 500)
        now = int(self.clock())
        with transaction(self.database_url) as c:
            self._enabled(c, guild)
            row = self._item(c, guild, item, locked=True)
            self._revision(row, revision)
            if row['status'] != 'closed' or row['config']['kind'] != 'giveaway' or row['round_number'] >= 20:
                raise RuntimeError('campaign_not_rerollable')
            c.execute("UPDATE giveaways SET status='closing',revision=revision+1,updated_at=%s WHERE id=%s", (now, item))
            c.execute('INSERT INTO giveaway_draw_jobs(campaign_id,round_number,actor_id,reason,available_at,created_at) VALUES(%s,%s,%s,%s,%s,%s)',
                      (item, row['round_number'] + 1, actor, reason, now, now))
            self._audit(c, item, actor, 'reroll_requested', now, {'reason': reason})
            return self._item(c, guild, item)

    def close(self, guild, item, actor, revision, reason):
        reason = text(reason, 'reason', 500)
        now = int(self.clock())
        with transaction(self.database_url) as c:
            self._enabled(c, guild)
            row = self._item(c, guild, item, locked=True)
            self._revision(row, revision)
            if row['status'] != 'open':
                raise RuntimeError('campaign_not_open')
            c.execute("UPDATE giveaways SET status='closing',revision=revision+1,updated_at=%s WHERE id=%s", (now, item))
            changed = c.execute("UPDATE giveaway_draw_jobs SET available_at=%s,actor_id=%s,reason=%s WHERE campaign_id=%s AND round_number=1 AND status IN ('pending','retry') AND lease_owner IS NULL", (now, actor, reason, item)).rowcount
            if changed != 1:
                raise RuntimeError('draw_not_schedulable')
            self._audit(c, item, actor, 'closed_early', now, {'reason': reason})
            self._queue(c, item, now)
            return self._item(c, guild, item)

    def retry(self, guild, item, actor, revision, job_id, *, draw=False):
        table = 'giveaway_draw_jobs' if draw else 'giveaway_outbox'
        now = int(self.clock())
        with transaction(self.database_url) as c:
            self._enabled(c, guild)
            row = self._item(c, guild, item, locked=True)
            self._revision(row, revision)
            if draw and row['status'] not in ('open', 'closing'):
                recorded = c.execute('SELECT 1 FROM giveaway_draws d JOIN giveaway_draw_jobs j ON j.campaign_id=d.campaign_id AND j.round_number=d.round_number WHERE j.id=%s AND j.campaign_id=%s', (job_id, item)).fetchone()
                if not recorded:
                    raise RuntimeError('campaign_not_drawable')
            changed = c.execute(f"UPDATE {table} SET status='pending',attempts=0,available_at=%s,completed_at=NULL,last_error=NULL WHERE id=%s AND campaign_id=%s AND status='failed' AND lease_owner IS NULL", (now, job_id, item)).rowcount
            if changed != 1:
                raise RuntimeError('job_not_retryable')
            self._audit(c, item, actor, 'draw_retry' if draw else 'publication_retry', now, {'job_id': job_id})

    def _owned(self, c, job, table):
        if table not in ('giveaway_outbox', 'giveaway_draw_jobs'):
            raise ValueError('Unsupported campaign queue')
        parent = c.execute('SELECT guild_id FROM giveaways WHERE id=%s', (job['campaign_id'],)).fetchone()
        if not parent:
            raise LostLease('Campaign no longer exists')
        self._enabled(c, parent['guild_id'])
        row = self._item(c, parent['guild_id'], job['campaign_id'], locked=True)
        lease = job['_lease']
        owned = c.execute(f"SELECT 1 FROM {table} WHERE id=%s AND campaign_id=%s AND status='processing' AND lease_owner=%s AND lease_token=%s AND lease_until>%s FOR UPDATE",
                          (job['id'], row['id'], lease['owner'], lease['token'], int(self.clock()))).fetchone()
        if not owned:
            raise LostLease('Campaign job ownership changed')
        return row

    def draw_plan(self, job):
        now = int(self.clock())
        with transaction(self.database_url) as c:
            row = self._owned(c, job, 'giveaway_draw_jobs')
            if row['status'] == 'open' and row['ends_at'] <= now:
                c.execute("UPDATE giveaways SET status='closing',revision=revision+1,updated_at=%s WHERE id=%s", (now, row['id']))
                row = self._item(c, row['guild_id'], row['id'])
            existing = c.execute('SELECT * FROM giveaway_draws WHERE campaign_id=%s AND round_number=%s', (row['id'], job['round_number'])).fetchone()
            if existing:
                return {'campaign': row, 'existing': existing, 'entrants': []}
            if row['status'] != 'closing' or job['round_number'] != row['round_number'] + 1:
                raise RuntimeError('draw_not_ready')
            entrants = c.execute('SELECT user_id FROM giveaway_entries WHERE campaign_id=%s AND active=1 ORDER BY joined_at,user_id', (row['id'],)).fetchall()
            return {'campaign': row, 'existing': None, 'entrants': [e['user_id'] for e in entrants]}

    def complete_draw(self, job, revision, eligible_ids, *, rng=None):
        now = int(self.clock())
        with transaction(self.database_url) as c:
            row = self._owned(c, job, 'giveaway_draw_jobs')
            existing = c.execute('SELECT * FROM giveaway_draws WHERE campaign_id=%s AND round_number=%s', (row['id'], job['round_number'])).fetchone()
            if existing:
                return existing
            self._revision(row, revision)
            if row['status'] != 'closing' or job['round_number'] != row['round_number'] + 1:
                raise RuntimeError('draw_not_ready')
            entrants = {e['user_id'] for e in c.execute('SELECT user_id FROM giveaway_entries WHERE campaign_id=%s AND active=1', (row['id'],))}
            eligible_ids = set(eligible_ids)
            if not eligible_ids <= entrants:
                raise ValueError('unknown_candidate')
            previous = [user for draw in c.execute('SELECT winners_json FROM giveaway_draws WHERE campaign_id=%s', (row['id'],)) for user in json.loads(draw['winners_json'])]
            pool, winners, digest = selection(eligible_ids, row['config']['winner_count'], previous=previous, rng=rng)
            result = c.execute('INSERT INTO giveaway_draws(campaign_id,round_number,actor_id,reason,candidates_json,winners_json,excluded_count,candidate_hash,created_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *',
                               (row['id'], job['round_number'], job['actor_id'], job['reason'], json.dumps(pool), json.dumps(winners), len(entrants) - len(pool), digest, now)).fetchone()
            c.execute("UPDATE giveaways SET status='closed',round_number=%s,revision=revision+1,updated_at=%s WHERE id=%s", (job['round_number'], now, row['id']))
            self._audit(c, row['id'], job['actor_id'], 'draw_completed' if row['config']['kind'] == 'giveaway' else 'registration_closed', now,
                        {'round': job['round_number'], 'candidate_hash': digest, 'eligible_count': len(pool), 'winner_count': len(winners)})
            self._queue(c, row['id'], now)
            return result

    def publication_plan(self, job):
        with transaction(self.database_url) as c:
            row = self._owned(c, job, 'giveaway_outbox')
            entrants = c.execute('SELECT count(*) AS n FROM giveaway_entries WHERE campaign_id=%s AND active=1', (row['id'],)).fetchone()['n']
            result = c.execute('SELECT * FROM giveaway_draws WHERE campaign_id=%s ORDER BY round_number DESC LIMIT 1', (row['id'],)).fetchone()
            return {'campaign': row, 'entrants': entrants, 'draw': result}

    def publication_begin(self, job):
        with transaction(self.database_url) as c:
            row = self._owned(c, job, 'giveaway_outbox')
            if row['message_id']:
                return 'edit'
            if row['delivery_started']:
                return 'recover'
            c.execute('UPDATE giveaways SET delivery_started=1 WHERE id=%s', (row['id'],))
            return 'send'

    def publication_receipt(self, job, message):
        message = snowflake(message, 'message_id')
        now = int(self.clock())
        with transaction(self.database_url) as c:
            row = self._owned(c, job, 'giveaway_outbox')
            if row['message_id'] not in (None, message):
                raise RuntimeError('publication_receipt_conflict')
            if row['message_id'] is None:
                c.execute('UPDATE giveaways SET message_id=%s WHERE id=%s', (message, row['id']))
                self._audit(c, row['id'], 0, 'publication_received', now)

    def publication_not_sent(self, job):
        with transaction(self.database_url) as c:
            row = self._owned(c, job, 'giveaway_outbox')
            if row['message_id'] is None:
                c.execute('UPDATE giveaways SET delivery_started=0 WHERE id=%s', (row['id'],))

    def publication_settled(self, job, revision):
        with transaction(self.database_url) as c:
            row = self._owned(c, job, 'giveaway_outbox')
            if row['revision'] != revision:
                self._queue(c, row['id'], int(self.clock()), except_job=job['id'])

    def history(self, guild, item):
        with transaction(self.database_url) as c:
            self._item(c, guild, item)
            events = c.execute('SELECT * FROM giveaway_events WHERE campaign_id=%s ORDER BY id DESC LIMIT 100', (item,)).fetchall()
            draws = c.execute('SELECT * FROM giveaway_draws WHERE campaign_id=%s ORDER BY round_number', (item,)).fetchall()
            entries = c.execute('SELECT * FROM giveaway_entries WHERE campaign_id=%s ORDER BY joined_at,user_id', (item,)).fetchall()
            delivery = c.execute('SELECT id,status,attempts,last_error FROM giveaway_outbox WHERE campaign_id=%s ORDER BY id DESC LIMIT 100', (item,)).fetchall()
            draw_jobs = c.execute('SELECT id,round_number,status,attempts,last_error FROM giveaway_draw_jobs WHERE campaign_id=%s ORDER BY id DESC LIMIT 20', (item,)).fetchall()
            return {'events': events, 'draws': draws, 'entries': entries, 'delivery': delivery, 'draw_jobs': draw_jobs}

    def purge_expired(self):
        now = int(self.clock())
        with transaction(self.database_url) as c:
            return c.execute('DELETE FROM giveaways WHERE id IN (SELECT p.id FROM giveaways p WHERE p.expires_at<=%s AND NOT EXISTS(SELECT 1 FROM giveaway_outbox j WHERE j.campaign_id=p.id AND j.lease_until>%s) AND NOT EXISTS(SELECT 1 FROM giveaway_draw_jobs j WHERE j.campaign_id=p.id AND j.lease_until>%s) ORDER BY p.expires_at LIMIT 100 FOR UPDATE SKIP LOCKED)', (now, now, now)).rowcount
