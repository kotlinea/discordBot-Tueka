"""PostgreSQL persistence for suggestions, votes, and review history."""
from __future__ import annotations

import json
import time
from database import require_current, transaction, lock_resource
from jobs import QueueRepository, QueueSpec, LostLease
from jobs.catalog import QUEUE_SPECS
from typing import Any
from discord_io import DiscordFailure
from .roadmap import labels as normalize_labels, merge as validate_merge


class SuggestionRepository:
    def __init__(self, database_url: str) -> None:
        from guild_settings import GuildSettingsRepository
        self.database_url = database_url
        require_current(self.database_url)
        self.outbox_jobs = QueueRepository(self.database_url, QUEUE_SPECS['suggestion_outbox'])
        self.settings = GuildSettingsRepository(database_url)

    @staticmethod
    def _queue(connection, suggestion_id: int, action: str, payload: dict | None = None):
        now = int(time.time())
        connection.execute('INSERT INTO suggestion_outbox(suggestion_id,action,payload_json,available_at,created_at) VALUES(%s,%s,%s,%s,%s)',
                           (suggestion_id, action, json.dumps(payload or {}), now, now))

    def delivery_state(self, item: dict, *, started: bool, failed: str | None = None):
        with self._connection() as connection:
            changed = connection.execute("""UPDATE suggestion_outbox SET delivery_started=%s WHERE id=%s AND status='processing'
                AND lease_owner=%s AND lease_token=%s AND lease_until>%s""",
                (int(started), item['id'], item['_lease']['owner'], item['_lease']['token'], int(time.time())))
            if changed.rowcount != 1:
                raise LostLease('Suggestion delivery ownership changed')
            if failed is not None:
                connection.execute("UPDATE suggestions SET status='delivery_failed',updated_at=%s,revision=revision+1 WHERE id=%s AND message_id IS NULL", (int(time.time()), item['suggestion_id']))
                connection.execute("""INSERT INTO suggestion_events(suggestion_id,guild_id,actor_id,event_type,detail_json,created_at)
                    SELECT id,guild_id,author_id,'delivery_failed',%s,%s FROM suggestions WHERE id=%s""",
                    (json.dumps({'error': failed[:300]}), int(time.time()), item['suggestion_id']))

    def publication_delivered(self, item: dict, message_id: int, *, discussion: bool = False):
        with self._connection() as connection:
            parent=connection.execute('SELECT guild_id FROM suggestions WHERE id=%s',(item['suggestion_id'],)).fetchone()
            if not parent:raise LostLease('Suggestion no longer exists')
            lock_resource(connection,'suggestion-merge',str(parent['guild_id']))
            owned = connection.execute("SELECT 1 FROM suggestion_outbox WHERE id=%s AND status='processing' AND lease_owner=%s AND lease_token=%s AND lease_until>%s FOR UPDATE",
                (item['id'], item['_lease']['owner'], item['_lease']['token'], int(time.time()))).fetchone()
            if not owned:
                raise LostLease('Suggestion delivery ownership changed')
            changed = connection.execute("UPDATE suggestions SET message_id=%s,status=CASE WHEN status='delivery_failed' THEN 'pending' ELSE status END,updated_at=%s,revision=revision+1 WHERE id=%s AND (message_id IS NULL OR message_id=%s)",
                (message_id, int(time.time()), item['suggestion_id'], message_id))
            if changed.rowcount != 1:
                raise DiscordFailure('Suggestion publication reference changed; reconciliation required', partial=True)
            self._queue(connection, item['suggestion_id'], 'sync')
            for child in connection.execute('SELECT id FROM suggestions WHERE guild_id=%s AND merged_into=%s',(parent['guild_id'],item['suggestion_id'])).fetchall():
                self._queue(connection,child['id'],'sync')
            if discussion:
                self._queue(connection, item['suggestion_id'], 'discussion')

    def discussion_delivered(self, item: dict, thread_id: int):
        with self._connection() as connection:
            owned = connection.execute("SELECT 1 FROM suggestion_outbox WHERE id=%s AND status='processing' AND lease_owner=%s AND lease_token=%s AND lease_until>%s FOR UPDATE",
                (item['id'], item['_lease']['owner'], item['_lease']['token'], int(time.time()))).fetchone()
            if not owned:
                raise LostLease('Suggestion delivery ownership changed')
            changed = connection.execute('UPDATE suggestions SET discussion_thread_id=%s,revision=revision+1,updated_at=%s WHERE id=%s AND (discussion_thread_id IS NULL OR discussion_thread_id=%s)',
                (thread_id, int(time.time()), item['suggestion_id'], thread_id))
            if changed.rowcount != 1:
                raise DiscordFailure('Suggestion discussion reference changed; reconciliation required', partial=True)
            self._queue(connection, item['suggestion_id'], 'sync')

    def delivery_suggestion(self, suggestion_id: int) -> dict | None:
        with self._connection() as connection:
            row = connection.execute('SELECT guild_id FROM suggestions WHERE id=%s', (suggestion_id,)).fetchone()
        return self.get(row['guild_id'], suggestion_id) if row else None

    def _connection(self):
        return transaction(self.database_url)

    @staticmethod
    def _item(row: dict[str, Any], *, upvotes: int = 0, downvotes: int = 0) -> dict[str, Any]:
        value = dict(row)
        value["answers"] = json.loads(value.pop("answers_json"))
        value['tags'] = json.loads(value.pop('tags_json','[]'))
        value["upvotes"], value["downvotes"] = upvotes, downvotes
        return value

    def create(self, guild_id: int, channel_id: int, author_id: int, answers: dict[str, str]) -> dict[str, Any]:
        now = int(time.time())
        with self._connection() as connection:
            retention=self.settings.get_module(guild_id,'suggestions',_conn=connection)['settings']['retention_days']
            cursor = connection.execute(
                "INSERT INTO suggestions(guild_id,channel_id,author_id,answers_json,created_at,updated_at,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING id",
                (guild_id, channel_id, author_id, json.dumps(answers, ensure_ascii=False), now, now, now+retention*86400),
            )
            suggestion_id = int(cursor.fetchone()["id"])
            connection.execute(
                "INSERT INTO suggestion_events(suggestion_id,guild_id,actor_id,event_type,created_at) VALUES(%s,%s,%s,%s,%s)",
                (suggestion_id, guild_id, author_id, "created", now),
            )
            self._queue(connection, suggestion_id, 'publish')
        item = self.get(guild_id, suggestion_id)
        assert item is not None
        return item

    def attach_message(self, guild_id: int, suggestion_id: int, message_id: int) -> dict[str, Any]:
        with self._connection() as connection:
            connection.execute(
                "UPDATE suggestions SET message_id=%s,updated_at=%s,revision=revision+1 WHERE guild_id=%s AND id=%s",
                (message_id, int(time.time()), guild_id, suggestion_id),
            )
        item = self.get(guild_id, suggestion_id)
        if item is None:
            raise LookupError("suggestion_not_found")
        return item

    def mark_delivery_failed(self, guild_id: int, suggestion_id: int, detail: str) -> None:
        now = int(time.time())
        with self._connection() as connection:
            connection.execute("UPDATE suggestions SET status='delivery_failed',updated_at=%s,revision=revision+1 WHERE guild_id=%s AND id=%s", (now, guild_id, suggestion_id))
            connection.execute(
                "INSERT INTO suggestion_events(suggestion_id,guild_id,actor_id,event_type,detail_json,created_at) SELECT id,guild_id,author_id,'delivery_failed',%s,%s FROM suggestions WHERE guild_id=%s AND id=%s",
                (json.dumps({"error": detail[:300]}, ensure_ascii=False), now, guild_id, suggestion_id),
            )

    def get(self, guild_id: int, suggestion_id: int) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM suggestions WHERE guild_id=%s AND id=%s AND (expires_at IS NULL OR expires_at>%s)", (guild_id, suggestion_id,int(time.time()))).fetchone()
            if row is None:
                return None
            counts = self._counts(connection,guild_id,[row['merged_into'] or row['id']])
        votes=counts.get(row['merged_into'] or row['id'],(0,0))
        return self._item(row,upvotes=votes[0],downvotes=votes[1])

    def list(self, guild_id: int, *, limit: int = 50, before: int | None = None, category: str | None=None, tag: str | None=None, status: str | None=None) -> list[dict[str, Any]]:
        clauses, values = ["guild_id=%s",'(expires_at IS NULL OR expires_at>%s)'], [guild_id,int(time.time())]
        if before is not None:
            clauses.append("id<%s")
            values.append(before)
        if category is not None:
            clauses.append('category=%s');values.append(category)
        if tag is not None:
            clauses.append('tags_json::jsonb @> %s::jsonb');values.append(json.dumps([tag]))
        if status is not None:
            if status not in {'pending','reviewing','approved','implemented','rejected','delivery_failed','merged'}:raise ValueError('invalid_status')
            clauses.append('status=%s');values.append(status)
        values.append(max(1, min(limit, 100)))
        with self._connection() as connection:
            rows = connection.execute(
                f"SELECT * FROM suggestions WHERE {' AND '.join(clauses)} ORDER BY id DESC LIMIT %s", values,
            ).fetchall()
            counts = self._counts(connection,guild_id,[row['merged_into'] or row['id'] for row in rows])
        return [self._item(row,upvotes=counts.get(row['merged_into'] or row['id'],(0,0))[0],downvotes=counts.get(row['merged_into'] or row['id'],(0,0))[1]) for row in rows]

    @staticmethod
    def _counts(c,guild,roots):
        if not roots:return {}
        rows=c.execute('''WITH effective AS (
            SELECT DISTINCT ON (COALESCE(s.merged_into,s.id),v.user_id)
                COALESCE(s.merged_into,s.id) AS root,v.value
            FROM suggestions s JOIN suggestion_votes v ON v.suggestion_id=s.id
            WHERE s.guild_id=%s AND COALESCE(s.merged_into,s.id)=ANY(%s)
                AND (s.expires_at IS NULL OR s.expires_at>%s)
            ORDER BY COALESCE(s.merged_into,s.id),v.user_id,(s.merged_into IS NULL) DESC,v.updated_at DESC,s.id DESC
        ) SELECT root,count(*) FILTER(WHERE value=1) AS upvotes,count(*) FILTER(WHERE value=-1) AS downvotes FROM effective GROUP BY root''',(guild,roots,int(time.time()))).fetchall()
        return {row['root']:(row['upvotes'],row['downvotes']) for row in rows}

    def vote(self, guild_id: int, suggestion_id: int, user_id: int, value: int) -> dict[str, Any]:
        if value not in {-1, 1}:
            raise ValueError("invalid_vote")
        now = int(time.time())
        with self._connection() as connection:
            # Serialize the status check and vote with staff review writes.
            lock_resource(connection,'suggestion-merge',str(guild_id))
            item = connection.execute("SELECT status FROM suggestions WHERE guild_id=%s AND id=%s AND (expires_at IS NULL OR expires_at>%s) FOR UPDATE", (guild_id, suggestion_id,now)).fetchone()
            if item is None:
                raise LookupError("suggestion_not_found")
            if item["status"] in {"approved", "rejected", "implemented", "delivery_failed",'merged'}:
                raise RuntimeError("suggestion_closed")
            current = connection.execute("SELECT value FROM suggestion_votes WHERE suggestion_id=%s AND user_id=%s", (suggestion_id, user_id)).fetchone()
            children=connection.execute('SELECT id FROM suggestions WHERE guild_id=%s AND merged_into=%s AND (expires_at IS NULL OR expires_at>%s)',(guild_id,suggestion_id,now)).fetchall()
            effective=current
            if not current and children:
                effective=connection.execute('SELECT value FROM suggestion_votes WHERE suggestion_id=ANY(%s) AND user_id=%s ORDER BY updated_at DESC,suggestion_id DESC LIMIT 1',([row['id'] for row in children],user_id)).fetchone()
            if effective and int(effective['value'])==value and children:
                connection.execute('INSERT INTO suggestion_votes(suggestion_id,user_id,value,created_at,updated_at) VALUES(%s,%s,0,%s,%s) ON CONFLICT(suggestion_id,user_id) DO UPDATE SET value=0,updated_at=excluded.updated_at',(suggestion_id,user_id,now,now))
                event_type='vote_removed'
            elif current and int(current["value"]) == value:
                connection.execute("DELETE FROM suggestion_votes WHERE suggestion_id=%s AND user_id=%s", (suggestion_id, user_id))
                event_type = "vote_removed"
            else:
                connection.execute(
                    "INSERT INTO suggestion_votes(suggestion_id,user_id,value,created_at,updated_at) VALUES(%s,%s,%s,%s,%s) ON CONFLICT(suggestion_id,user_id) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",
                    (suggestion_id, user_id, value, now, now),
                )
                event_type = "vote_cast"
            connection.execute(
                "INSERT INTO suggestion_events(suggestion_id,guild_id,actor_id,event_type,detail_json,created_at) VALUES(%s,%s,%s,%s,%s,%s)",
                (suggestion_id, guild_id, user_id, event_type, json.dumps({"value": value}), now),
            )
            self._queue(connection, suggestion_id, 'sync')
            for child in children:
                self._queue(connection,child['id'],'sync')
        result = self.get(guild_id, suggestion_id)
        assert result is not None
        return result

    def review(self, guild_id: int, suggestion_id: int, reviewer_id: int, status: str,
               reason: str = '', *, expected_revision: int | None = None) -> dict[str, Any]:
        if status not in {"reviewing", "approved", "rejected", "implemented"}:
            raise ValueError("invalid_status")
        reason = reason.strip()
        if not reason or len(reason) > 1000:
            raise ValueError('invalid_reason')
        now = int(time.time())
        with self._connection() as connection:
            previous = connection.execute('SELECT status,revision FROM suggestions WHERE guild_id=%s AND id=%s AND (expires_at IS NULL OR expires_at>%s) FOR UPDATE',
                (guild_id, suggestion_id,now)).fetchone()
            if previous is None:
                raise LookupError('suggestion_not_found')
            if expected_revision is not None and previous['revision'] != expected_revision:
                raise RuntimeError('revision_conflict')
            allowed = {'approved'} if status == 'implemented' else {'pending', 'reviewing'}
            if previous['status'] not in allowed:
                raise RuntimeError('suggestion_closed')
            cursor = connection.execute(
                "UPDATE suggestions SET status=%s,reviewer_id=%s,review_reason=%s,reviewed_at=%s,implemented_at=CASE WHEN %s='implemented' THEN %s ELSE implemented_at END,updated_at=%s,revision=revision+1 WHERE guild_id=%s AND id=%s",
                (status, reviewer_id, reason, now, status, now, now, guild_id, suggestion_id),
            )
            if not cursor.rowcount:
                exists = connection.execute("SELECT 1 FROM suggestions WHERE guild_id=%s AND id=%s", (guild_id, suggestion_id)).fetchone()
                if exists:
                    raise RuntimeError("suggestion_closed")
                raise LookupError("suggestion_not_found")
            connection.execute(
                "INSERT INTO suggestion_events(suggestion_id,guild_id,actor_id,event_type,detail_json,created_at) VALUES(%s,%s,%s,%s,%s,%s)",
                (suggestion_id, guild_id, reviewer_id, "status_changed", json.dumps({"status": status, 'previous_status': previous['status'], 'reason': reason}, ensure_ascii=False), now),
            )
            self._queue(connection, suggestion_id, 'sync')
            self._queue(connection, suggestion_id, 'review_log', {'status': status, 'reviewer_id': reviewer_id, 'review_reason': reason})
        result = self.get(guild_id, suggestion_id)
        assert result is not None
        return result

    def events(self, guild_id: int, suggestion_id: int, *, before: int | None = None, limit: int = 50) -> list[dict]:
        with self._connection() as connection:
            exists = connection.execute('SELECT 1 FROM suggestions WHERE guild_id=%s AND id=%s AND (expires_at IS NULL OR expires_at>%s)', (guild_id, suggestion_id,int(time.time()))).fetchone()
            if not exists:
                raise LookupError('suggestion_not_found')
            rows = connection.execute('SELECT id,actor_id,event_type,detail_json,created_at FROM suggestion_events WHERE guild_id=%s AND suggestion_id=%s AND (%s::bigint IS NULL OR id<%s) ORDER BY id DESC LIMIT %s',
                (guild_id, suggestion_id, before, before, max(1, min(limit, 100)))).fetchall()
        return [{**{k:v for k,v in row.items() if k != 'detail_json'}, 'detail': json.loads(row['detail_json'])} for row in rows]

    def _roadmap_enabled(self,c,guild):
        lock_resource(c,'guild-module',f'{guild}:suggestions')
        module=self.settings.get_module(guild,'suggestions',_conn=c)
        if not module['enabled']:raise PermissionError('suggestions_disabled')
        return module['settings']

    @staticmethod
    def _roadmap_event(c,guild,item,actor,kind,detail,now):
        c.execute('INSERT INTO suggestion_events(suggestion_id,guild_id,actor_id,event_type,detail_json,created_at) VALUES(%s,%s,%s,%s,%s,%s)',(item,guild,actor,kind,json.dumps(detail,ensure_ascii=False),now))

    def set_labels(self,guild,item,actor,category,tags,revision):
        now=int(time.time())
        with self._connection() as c:
            settings=self._roadmap_enabled(c,guild)
            values=normalize_labels(category,tags,settings)
            row=c.execute('SELECT * FROM suggestions WHERE guild_id=%s AND id=%s AND (expires_at IS NULL OR expires_at>%s) FOR UPDATE',(guild,item,now)).fetchone()
            if not row:raise LookupError('suggestion_not_found')
            if row['revision']!=revision:raise RuntimeError('revision_conflict')
            c.execute('UPDATE suggestions SET category=%s,tags_json=%s,revision=revision+1,updated_at=%s WHERE id=%s',(values['category'],json.dumps(values['tags'],ensure_ascii=False),now,item))
            self._roadmap_event(c,guild,item,actor,'labels_changed',{'previous_category':row['category'],'previous_tags':json.loads(row['tags_json']),**values},now)
            self._queue(c,item,'sync')
        return self.get(guild,item)

    def merge(self,guild,source_id,target_id,actor,reason,source_revision,target_revision):
        now=int(time.time())
        with self._connection() as c:
            self._roadmap_enabled(c,guild)
            lock_resource(c,'suggestion-merge',str(guild))
            rows=c.execute('SELECT * FROM suggestions WHERE guild_id=%s AND id=ANY(%s) ORDER BY id FOR UPDATE',(guild,[source_id,target_id])).fetchall()
            by_id={row['id']:row for row in rows}
            if source_id not in by_id or target_id not in by_id:raise LookupError('suggestion_not_found')
            source,target=by_id[source_id],by_id[target_id]
            reason=validate_merge(source,target,reason,source_revision,target_revision,now)
            descendants=c.execute('SELECT id,merged_into FROM suggestions WHERE guild_id=%s AND merged_into=ANY(%s) ORDER BY id FOR UPDATE',(guild,[source_id,target_id])).fetchall()
            if len(descendants)+1>100:raise ValueError('merge_source_limit')
            children=[row['id'] for row in descendants if row['merged_into']==source_id]
            c.execute("UPDATE suggestions SET merged_into=%s,status='merged',revision=revision+1,updated_at=%s WHERE id=%s",(target_id,now,source_id))
            c.execute('UPDATE suggestions SET revision=revision+1,updated_at=%s WHERE id=%s',(now,target_id))
            self._roadmap_event(c,guild,source_id,actor,'merged',{'target_id':target_id,'reason':reason,'previous_status':source['status']},now)
            self._roadmap_event(c,guild,target_id,actor,'duplicate_added',{'source_id':source_id,'reason':reason},now)
            for child in children:
                c.execute('UPDATE suggestions SET merged_into=%s,revision=revision+1,updated_at=%s WHERE id=%s',(target_id,now,child))
                self._roadmap_event(c,guild,child,actor,'merge_retargeted',{'previous_target_id':source_id,'target_id':target_id,'reason':reason},now)
            for item in (source_id,target_id,*children):self._queue(c,item,'sync')
        return self.get(guild,source_id)

    def purge_expired(self,now=None):
        now=int(time.time()) if now is None else now
        total=0
        with self._connection() as c:
            guilds=c.execute('SELECT DISTINCT guild_id FROM suggestions WHERE expires_at<=%s ORDER BY guild_id LIMIT 50',(now,)).fetchall()
        for guild in guilds:
            with self._connection() as c:
                # Votes and merges queue related posts; take the same Guild lock before row locks.
                lock_resource(c,'suggestion-merge',str(guild['guild_id']))
                rows=c.execute('''SELECT s.id,s.merged_into FROM suggestions s WHERE s.guild_id=%s AND s.expires_at<=%s
                    AND NOT EXISTS(SELECT 1 FROM suggestion_outbox j WHERE j.suggestion_id=s.id AND j.lease_until>%s)
                    ORDER BY s.expires_at LIMIT %s FOR UPDATE SKIP LOCKED''',(guild['guild_id'],now,now,500-total)).fetchall()
                if not rows:continue
                c.execute('DELETE FROM suggestions WHERE id=ANY(%s)',([row['id'] for row in rows],))
                parents={row['merged_into'] for row in rows if row['merged_into']}
                for parent in parents:
                    family=c.execute('SELECT id FROM suggestions WHERE guild_id=%s AND (id=%s OR merged_into=%s) AND (expires_at IS NULL OR expires_at>%s)',(guild['guild_id'],parent,parent,now)).fetchall()
                    for related in family:self._queue(c,related['id'],'sync')
                total+=len(rows)
            if total>=500:break
        return total
