"""Guild-fenced aggregate counters and one leased observer per guild."""
import time

from database import lock_resource, require_current, transaction
from guild_settings import GuildSettingsRepository
from .models import DAY, MAX_GAP, day_key, integer, normalize, period, segments, snowflake, timestamp


class InsightsRepository:
    def __init__(self, database_url, *, clock=time.time):
        self.database_url, self.clock = database_url, clock
        require_current(database_url)
        self.settings = GuildSettingsRepository(database_url)

    def _module(self, c, guild):
        snowflake(guild)
        lock_resource(c, 'guild-module', f'{guild}:insights')
        module = self.settings.get_module(guild, 'insights', _conn=c)
        return module, normalize(module['settings'])

    @staticmethod
    def _owner(owner):
        if not isinstance(owner, str) or not owner or len(owner) > 100:
            raise ValueError('observer_owner')

    def claim(self, guild, owner):
        self._owner(owner)
        now = timestamp(int(self.clock()))
        with transaction(self.database_url) as c:
            module, _ = self._module(c, guild)
            if not module['enabled']:
                return False
            old = c.execute('SELECT * FROM insights_observers WHERE guild_id=%s FOR UPDATE', (guild,)).fetchone()
            if old and old['owner'] != owner and old['last_seen'] + MAX_GAP >= now:
                return False
            if old and old['last_seen'] > now:
                raise ValueError('clock_reversed')
            c.execute('DELETE FROM insights_voice WHERE guild_id=%s', (guild,))
            c.execute('INSERT INTO insights_observers(guild_id,owner,revision,last_seen) VALUES(%s,%s,%s,%s) ON CONFLICT(guild_id) DO UPDATE SET owner=excluded.owner,revision=excluded.revision,last_seen=excluded.last_seen',
                      (guild, owner, module['revision'], now))
            return True

    def _active(self, c, guild, owner, now):
        self._owner(owner)
        module, config = self._module(c, guild)
        if not module['enabled']:
            return None, config
        row = c.execute('SELECT * FROM insights_observers WHERE guild_id=%s FOR UPDATE', (guild,)).fetchone()
        if not row or row['owner'] != owner:
            return None, config
        if row['last_seen'] > now:
            raise ValueError('clock_reversed')
        if row['revision'] != module['revision']:
            # OFF/ON and collection changes establish a new observation boundary.
            c.execute('DELETE FROM insights_voice WHERE guild_id=%s', (guild,))
            c.execute('UPDATE insights_observers SET revision=%s,last_seen=%s WHERE guild_id=%s', (module['revision'], now, guild))
            row = {**row, 'revision': module['revision'], 'last_seen': now}
        return row, config

    @staticmethod
    def _add(c, guild, config, day, now, *, observed_since=None, **values):
        names = ('messages', 'joins', 'leaves', 'voice_seconds', 'observed_seconds')
        if set(values) - set(names) or any(type(v) is not int or v < 0 for v in values.values()):
            raise ValueError('aggregate')
        # Fixed UTC-day expiry; a later update cannot extend an existing record.
        from datetime import date
        start = (date.fromisoformat(day) - date(1970, 1, 1)).days * DAY
        first = max(start, min(now if observed_since is None else observed_since, start + DAY - 1))
        last = min(now, start + DAY - 1)
        c.execute('''INSERT INTO insights_daily(guild_id,day,messages,joins,leaves,voice_seconds,observed_seconds,first_observed,last_observed,expires_at)
          VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT(guild_id,day) DO UPDATE SET
          messages=insights_daily.messages+excluded.messages,joins=insights_daily.joins+excluded.joins,
          leaves=insights_daily.leaves+excluded.leaves,voice_seconds=insights_daily.voice_seconds+excluded.voice_seconds,
          observed_seconds=insights_daily.observed_seconds+excluded.observed_seconds,
          first_observed=LEAST(insights_daily.first_observed,excluded.first_observed),
          last_observed=GREATEST(insights_daily.last_observed,excluded.last_observed),
          expires_at=LEAST(insights_daily.expires_at,excluded.expires_at)''',
          (guild, day, *(values.get(k, 0) for k in names), first, last, start + config['retention_days'] * DAY))

    def event(self, guild, owner, kind, key, *, channel=None, occurred_at=None):
        if kind not in ('messages', 'joins', 'leaves') or not isinstance(key, str) or not 1 <= len(key) <= 100:
            raise ValueError('event')
        now = timestamp(int(self.clock()))
        happened = now if occurred_at is None else timestamp(occurred_at)
        if happened > now or now - happened > MAX_GAP:
            return False
        if kind == 'messages':
            channel = snowflake(channel)
        with transaction(self.database_url) as c:
            row, config = self._active(c, guild, owner, now)
            if not row or now - row['last_seen'] > MAX_GAP:
                return False
            if kind == 'messages' and channel not in config['channel_ids']:
                return False
            if kind != 'messages' and not config['track_members']:
                return False
            if day_key(happened) < day_key(max(0, now - (config['retention_days'] - 1) * DAY)):
                return False
            inserted = c.execute('INSERT INTO insights_seen(guild_id,event_key,observed_at,expires_at) VALUES(%s,%s,%s,%s) ON CONFLICT DO NOTHING RETURNING event_key',
                                 (guild, f'{kind}:{key}', now, min(now + DAY, (happened // DAY + config['retention_days']) * DAY))).fetchone()
            if not inserted:
                return False
            self._add(c, guild, config, day_key(happened), now, observed_since=happened, **{kind: 1})
            return True

    def heartbeat(self, guild, owner, voice):
        """Fresh eligible voice snapshot; never bridge a missing interval or channel move."""
        if not isinstance(voice, dict):
            raise ValueError('voice_snapshot')
        voice = {snowflake(user): snowflake(channel) for user, channel in voice.items()}
        now = timestamp(int(self.clock()))
        with transaction(self.database_url) as c:
            row, config = self._active(c, guild, owner, now)
            if not row:
                return False
            for day, seconds in segments(row['last_seen'], now):
                self._add(c, guild, config, day, now, observed_since=row['last_seen'], observed_seconds=seconds)
            self._add(c, guild, config, day_key(now), now)
            current = {r['user_id']: r for r in c.execute('SELECT * FROM insights_voice WHERE guild_id=%s', (guild,))}
            voice = {user: channel for user, channel in voice.items() if channel in config['channel_ids']}
            for user, channel in voice.items():
                old = current.get(user)
                if old and old['channel_id'] == channel and now - row['last_seen'] <= MAX_GAP:
                    for day, seconds in segments(old['last_seen'], now):
                        self._add(c, guild, config, day, now, observed_since=old['last_seen'], voice_seconds=seconds)
                c.execute('INSERT INTO insights_voice(guild_id,user_id,channel_id,last_seen) VALUES(%s,%s,%s,%s) ON CONFLICT(guild_id,user_id) DO UPDATE SET channel_id=excluded.channel_id,last_seen=excluded.last_seen',
                          (guild, user, channel, now))
            c.execute('DELETE FROM insights_voice WHERE guild_id=%s AND NOT (user_id=ANY(%s))', (guild, list(voice)))
            c.execute('UPDATE insights_observers SET last_seen=%s WHERE guild_id=%s', (now, guild))
            return True

    def voice_change(self, guild, owner, user, before, after):
        user = snowflake(user)
        before = None if before is None else snowflake(before)
        after = None if after is None else snowflake(after)
        now = timestamp(int(self.clock()))
        with transaction(self.database_url) as c:
            row, config = self._active(c, guild, owner, now)
            if not row:
                return False
            old = c.execute('SELECT * FROM insights_voice WHERE guild_id=%s AND user_id=%s', (guild, user)).fetchone()
            if old and old['last_seen'] > now:
                raise ValueError('clock_reversed')
            if old and before != after and old['channel_id'] == after:
                # A replayed move already reflected by a previous event/snapshot.
                return True
            if old and old['channel_id'] == before and now - row['last_seen'] <= MAX_GAP:
                for day, seconds in segments(old['last_seen'], now):
                    self._add(c, guild, config, day, now, observed_since=old['last_seen'], voice_seconds=seconds)
            if after in config['channel_ids']:
                c.execute('INSERT INTO insights_voice(guild_id,user_id,channel_id,last_seen) VALUES(%s,%s,%s,%s) ON CONFLICT(guild_id,user_id) DO UPDATE SET channel_id=excluded.channel_id,last_seen=excluded.last_seen',
                          (guild, user, after, now))
            else:
                c.execute('DELETE FROM insights_voice WHERE guild_id=%s AND user_id=%s', (guild, user))
            return True

    def release(self, guild, owner):
        with transaction(self.database_url) as c:
            self._module(c, guild)
            c.execute('DELETE FROM insights_observers WHERE guild_id=%s AND owner=%s', (guild, owner))

    def _purge(self, c, guild, config, now):
        cutoff = day_key(max(0, now - (config['retention_days'] - 1) * DAY))
        count = c.execute('DELETE FROM insights_daily WHERE guild_id=%s AND (day<%s OR expires_at<=%s)', (guild, cutoff, now)).rowcount
        count += c.execute('DELETE FROM insights_seen WHERE guild_id=%s AND (expires_at<=%s OR observed_at<%s)',
                           (guild, now, max(0, now // DAY - config['retention_days'] + 1) * DAY)).rowcount
        count += c.execute('DELETE FROM insights_voice WHERE guild_id=%s AND last_seen<%s', (guild, now - MAX_GAP)).rowcount
        count += c.execute('DELETE FROM insights_observers WHERE guild_id=%s AND last_seen<%s', (guild, now - MAX_GAP)).rowcount
        return count

    def purge(self, *, after=0, limit=100):
        integer(after, 'after', 0, 2**63 - 1)
        integer(limit, 'limit', 1, 100)
        now = timestamp(int(self.clock()))
        with transaction(self.database_url) as c:
            ids = [r['guild_id'] for r in c.execute('SELECT guild_id FROM (SELECT guild_id FROM insights_daily UNION SELECT guild_id FROM insights_seen UNION SELECT guild_id FROM insights_observers) g WHERE guild_id>%s ORDER BY guild_id LIMIT %s', (after, limit))]
        removed = 0
        for guild in ids:
            with transaction(self.database_url) as c:
                _, config = self._module(c, guild)
                removed += self._purge(c, guild, config, now)
        return {'removed': removed, 'cursor': ids[-1] if len(ids) == limit else 0}

    def report(self, guild, start, end):
        now = timestamp(int(self.clock()))
        with transaction(self.database_url) as c:
            module, config = self._module(c, guild)
            days = period(start, end, now, config['retention_days'])
            rows = {r['day']: r for r in c.execute('SELECT * FROM insights_daily WHERE guild_id=%s AND day=ANY(%s) AND expires_at>%s ORDER BY day', (guild, days, now))}
            observer = c.execute('SELECT last_seen,revision FROM insights_observers WHERE guild_id=%s', (guild,)).fetchone()
        names = ('messages', 'joins', 'leaves', 'voice_seconds', 'observed_seconds')
        return {'enabled': module['enabled'], 'timezone': 'UTC', 'retention_days': config['retention_days'],
                'collecting': bool(module['enabled'] and observer and observer['revision'] == module['revision'] and 0 <= now - observer['last_seen'] <= MAX_GAP),
                'last_observed': observer['last_seen'] if observer else None,
                'days': [{'day': day, 'observed': day in rows,
                          **{key: rows[day][key] if day in rows else None for key in names},
                          'first_observed': rows[day]['first_observed'] if day in rows else None,
                          'last_observed': rows[day]['last_observed'] if day in rows else None} for day in days]}
