"""Transactional form configuration, immutable intake snapshots and review audit."""
import json
import time
from database import require_current, transaction, lock_resource
from guild_settings import GuildSettingsRepository
from .models import validate_form
from .service import intake, review_transition


class ApplicationRepository:
    def __init__(self, url):
        self.database_url = url
        require_current(url)
        self.settings = GuildSettingsRepository(url)

    def _enabled(self, c, guild):
        lock_resource(c, 'guild-module', f'{guild}:applications')
        if not self.settings.get_module(guild, 'applications', _conn=c)['enabled']:
            raise PermissionError('applications_disabled')

    @staticmethod
    def _form(row):
        if not row:
            raise LookupError('form_not_found')
        return {**json.loads(row['config_json']), **{k:v for k,v in row.items() if k != 'config_json'}, 'enabled':bool(row['enabled'])}

    @staticmethod
    def _item(row):
        if not row:
            raise LookupError('application_not_found')
        return {**{k:v for k,v in row.items() if k not in ('answers_json','snapshot_json')},
                'answers':json.loads(row['answers_json']), 'snapshot':json.loads(row['snapshot_json'])}

    def forms(self, guild):
        with transaction(self.database_url) as c:
            return [self._form(r) for r in c.execute('SELECT * FROM application_forms WHERE guild_id=%s ORDER BY id', (guild,)).fetchall()]

    def form(self, guild, form_id):
        with transaction(self.database_url) as c:
            return self._form(c.execute('SELECT * FROM application_forms WHERE guild_id=%s AND id=%s', (guild,form_id)).fetchone())

    def save_form(self, guild, actor, raw, *, form_id=None, revision=None):
        config, now = validate_form(raw), int(time.time())
        with transaction(self.database_url) as c:
            lock_resource(c, 'application-forms', str(guild))
            if form_id is None:
                if c.execute('SELECT COUNT(*) AS n FROM application_forms WHERE guild_id=%s', (guild,)).fetchone()['n'] >= 100:
                    raise ValueError('form_limit')
                row = c.execute('INSERT INTO application_forms(guild_id,config_json,enabled,created_at,updated_at) VALUES(%s,%s,%s,%s,%s) RETURNING *',
                    (guild,json.dumps(config),int(config['enabled']),now,now)).fetchone()
            else:
                previous = c.execute('SELECT * FROM application_forms WHERE guild_id=%s AND id=%s FOR UPDATE', (guild,form_id)).fetchone()
                if not previous:
                    raise LookupError('form_not_found')
                if previous['revision'] != revision:
                    raise RuntimeError('revision_conflict')
                row = c.execute('UPDATE application_forms SET config_json=%s,enabled=%s,revision=revision+1,updated_at=%s WHERE id=%s RETURNING *',
                    (json.dumps(config),int(config['enabled']),now,form_id)).fetchone()
            c.execute('INSERT INTO application_form_events(form_id,actor_id,revision,created_at) VALUES(%s,%s,%s,%s)', (row['id'],actor,row['revision'],now))
            return self._form(row)

    def submit(self, guild, form_id, author, interaction_id, answers, *, revision, roles, created_at, joined_at):
        now = int(time.time())
        with transaction(self.database_url) as c:
            self._enabled(c,guild)
            row = c.execute('SELECT * FROM application_forms WHERE guild_id=%s AND id=%s FOR UPDATE', (guild,form_id)).fetchone()
            form = self._form(row)
            normalized = intake(form,answers,revision=revision,roles=roles,created_at=created_at,joined_at=joined_at,now=now)
            duplicate = c.execute('SELECT * FROM applications WHERE interaction_id=%s', (interaction_id,)).fetchone()
            if duplicate:
                if duplicate['guild_id'] != guild or duplicate['author_id'] != author or duplicate['form_id'] != form_id:
                    raise PermissionError('interaction_mismatch')
                if duplicate['expires_at'] <= now:
                    raise RuntimeError('application_expired')
                return self._item(duplicate)
            previous = c.execute('SELECT status,created_at,expires_at FROM applications WHERE guild_id=%s AND form_id=%s AND author_id=%s ORDER BY id DESC LIMIT 1',
                (guild,form_id,author)).fetchone()
            if previous and previous['expires_at'] > now and previous['status'] in ('pending','reviewing'):
                raise RuntimeError('application_open')
            if previous and now < previous['created_at'] + form['cooldown_seconds']:
                raise RuntimeError('application_cooldown')
            # Expired pending entries cannot block the partial unique index.
            c.execute('DELETE FROM applications WHERE form_id=%s AND author_id=%s AND expires_at<=%s', (form_id,author,now))
            row = c.execute('INSERT INTO applications(guild_id,form_id,author_id,interaction_id,snapshot_json,answers_json,created_at,updated_at,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *',
                (guild,form_id,author,interaction_id,json.dumps(form),json.dumps(normalized),now,now,now+form['retention_days']*86400)).fetchone()
            c.execute("INSERT INTO application_events(application_id,actor_id,event_type,created_at) VALUES(%s,%s,'submitted',%s)", (row['id'],author,now))
            return self._item(row)

    def items(self, guild, *, author=None, before=None, limit=50):
        with transaction(self.database_url) as c:
            rows = c.execute('SELECT * FROM applications WHERE guild_id=%s AND expires_at>%s AND (%s::bigint IS NULL OR author_id=%s) AND (%s::bigint IS NULL OR id<%s) ORDER BY id DESC LIMIT %s',
                (guild,int(time.time()),author,author,before,before,max(1,min(limit,100)))).fetchall()
            return [self._item(r) for r in rows]

    def events(self, guild, item_id):
        with transaction(self.database_url) as c:
            if not c.execute('SELECT 1 FROM applications WHERE guild_id=%s AND id=%s AND expires_at>%s', (guild,item_id,int(time.time()))).fetchone():
                raise LookupError('application_not_found')
            return c.execute('SELECT id,actor_id,event_type,reason,created_at FROM application_events WHERE application_id=%s ORDER BY id DESC LIMIT 100', (item_id,)).fetchall()

    def transition(self, guild, item_id, actor, status, reason, *, revision, withdraw=False):
        reason = reason.strip()
        now = int(time.time())
        with transaction(self.database_url) as c:
            self._enabled(c,guild)
            row = c.execute('SELECT * FROM applications WHERE guild_id=%s AND id=%s AND expires_at>%s FOR UPDATE', (guild,item_id,now)).fetchone()
            if not row:
                raise LookupError('application_not_found')
            review_transition(row,actor,status,reason,revision=revision,withdraw=withdraw)
            row = c.execute('UPDATE applications SET status=%s,revision=revision+1,updated_at=%s WHERE id=%s RETURNING *', (status,now,item_id)).fetchone()
            c.execute('INSERT INTO application_events(application_id,actor_id,event_type,reason,created_at) VALUES(%s,%s,%s,%s,%s)', (item_id,actor,status,reason if not withdraw else '',now))
            return self._item(row)

    def purge_expired(self, *, now=None):
        with transaction(self.database_url) as c:
            # Bounded batches; all Guilds, including disabled ones. Cascades answers' audit.
            return c.execute('DELETE FROM applications WHERE id IN (SELECT id FROM applications WHERE expires_at<=%s ORDER BY expires_at LIMIT 500)', (int(time.time()) if now is None else now,)).rowcount
