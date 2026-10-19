"""Board configuration, source observations, receipts and audit transactions."""
import json
import time
import uuid
from database import require_current,transaction,lock_resource
from jobs import QueueRepository,QueueSpec,LostLease
from .models import normalize,eligible,integer


class ModuleQueue(QueueRepository):
    def _claim_scope(self):
        if self.spec.table=='starboard_outbox':guild='(SELECT guild_id FROM starboard_entries WHERE id=starboard_outbox.entry_id)'
        elif self.spec.table=='starboard_refresh_jobs':guild='starboard_refresh_jobs.guild_id'
        else:raise ValueError('Unsupported Starboard queue')
        return f' AND EXISTS(SELECT 1 FROM guild_modules g WHERE g.guild_id={guild} AND g.module_id=%s AND g.enabled=1)',('starboard',)


class StarboardQueue(ModuleQueue):
    def purge(self,**_):return 0  # Entry retention owns cascading job cleanup.


class SourceQueue(ModuleQueue):
    def purge(self,**_):return super().purge(retention_seconds=86400)


class StarboardRepository:
    def __init__(self,url,*,clock=time.time):
        require_current(url)
        from guild_settings import GuildSettingsRepository
        self.database_url,self.clock=url,clock
        self.settings=GuildSettingsRepository(url)
        self.jobs=StarboardQueue(url,QueueSpec('starboard_outbox'),clock=clock)
        self.refresh_jobs=SourceQueue(url,QueueSpec('starboard_refresh_jobs'),clock=clock)

    def enqueue_refresh(self,guild,channel,message,*,known_channel=False,parent=None,reaction=None):
        now=int(self.clock())
        with transaction(self.database_url) as c:
            self._enabled(c,guild)
            boards=[json.loads(row['config_json']) for row in c.execute('SELECT config_json FROM starboards WHERE guild_id=%s',(guild,)).fetchall()]
            candidates=[config for config in boards if config['enabled'] and (reaction is None or config['emoji']==reaction)]
            if not candidates:return
            if known_channel and not any({channel,parent}&set(config['source_channel_ids']) and not {channel,parent}&set(config['excluded_channel_ids']) and channel!=config['target_channel_id'] for config in candidates):return
            lock_resource(c,'starboard-refresh',f'{guild}:{channel}:{message}')
            if c.execute("SELECT 1 FROM starboard_refresh_jobs WHERE guild_id=%s AND channel_id=%s AND message_id=%s AND status IN ('pending','retry')",(guild,channel,message)).fetchone():return
            if c.execute("SELECT count(*) AS n FROM starboard_refresh_jobs WHERE guild_id=%s AND status IN ('pending','retry','processing')",(guild,)).fetchone()['n']>=1000:raise ValueError('refresh_backlog_limit')
            # A new pending observation is retained if an older fetch is already
            # processing. A later retry may duplicate reads, never publications.
            c.execute('INSERT INTO starboard_refresh_jobs(guild_id,channel_id,message_id,available_at,created_at) VALUES(%s,%s,%s,%s,%s)',(guild,channel,message,now,now))

    def _enabled(self,c,guild):
        lock_resource(c,'guild-module',f'{guild}:starboard')
        if not self.settings.get_module(guild,'starboard',_conn=c)['enabled']:raise PermissionError('starboard_disabled')

    @staticmethod
    def _board(c,guild,board,*,locked=False):
        row=c.execute('SELECT * FROM starboards WHERE guild_id=%s AND id=%s'+(' FOR UPDATE' if locked else ''),(guild,board)).fetchone()
        if not row:raise LookupError('board_not_found')
        return {**row,'config':json.loads(row['config_json'])}

    @staticmethod
    def _audit(c,board,actor,event,now,detail=None,entry=None):
        c.execute('INSERT INTO starboard_events(board_id,entry_id,actor_id,event_type,detail_json,created_at) VALUES(%s,%s,%s,%s,%s,%s)',(board,entry,actor,event,json.dumps(detail or {}),now))

    @staticmethod
    def _queue(c,entry,now,*,except_job=None):
        # A processing job may have already checked its revision. Keep a durable
        # successor while coalescing changes into work that has not started.
        if not c.execute("SELECT 1 FROM starboard_outbox WHERE entry_id=%s AND status IN ('pending','retry') AND (%s::bigint IS NULL OR id<>%s)",(entry,except_job,except_job)).fetchone():
            c.execute('INSERT INTO starboard_outbox(entry_id,available_at,created_at) VALUES(%s,%s,%s)',(entry,now,now))

    def boards(self,guild):
        with transaction(self.database_url) as c:
            return [{**r,'config':json.loads(r['config_json'])} for r in c.execute('SELECT * FROM starboards WHERE guild_id=%s ORDER BY id',(guild,)).fetchall()]

    def board(self,guild,board):
        with transaction(self.database_url) as c:return self._board(c,guild,board)

    def save_board(self,guild,actor,values,*,board=None,revision=None,request_key=None):
        config=normalize(values);now=int(self.clock())
        with transaction(self.database_url) as c:
            self._enabled(c,guild);lock_resource(c,'starboard-config',str(guild))
            if board is None:
                request_key=uuid.uuid4().hex if request_key is None else request_key
                if not isinstance(request_key,str) or not 1<=len(request_key)<=100:raise ValueError('invalid_request_key')
                previous=c.execute('SELECT * FROM starboards WHERE guild_id=%s AND request_key=%s FOR UPDATE',(guild,request_key)).fetchone()
                if previous:
                    if previous['actor_id']!=actor or json.loads(previous['config_json'])!=config:raise RuntimeError('request_key_conflict')
                    return {**previous,'config':config}
                count=c.execute('SELECT count(*) AS n FROM starboards WHERE guild_id=%s',(guild,)).fetchone()['n']
                if count>=10:raise ValueError('board_limit')
                row=c.execute('INSERT INTO starboards(guild_id,actor_id,request_key,config_json,created_at,updated_at) VALUES(%s,%s,%s,%s,%s,%s) RETURNING *',(guild,actor,request_key,json.dumps(config),now,now)).fetchone()
                board=row['id'];event='board_created'
            else:
                old=self._board(c,guild,board,locked=True)
                if type(revision) is not int or old['revision']!=revision:raise RuntimeError('revision_conflict')
                row=c.execute('UPDATE starboards SET config_json=%s,revision=revision+1,updated_at=%s WHERE id=%s RETURNING *',(json.dumps(config),now,board)).fetchone();event='board_updated'
                # Workers re-read current routing; old target receipts remain available for cleanup.
                for entry in c.execute('SELECT id FROM starboard_entries WHERE board_id=%s AND expires_at>%s ORDER BY id FOR UPDATE',(board,now)).fetchall():
                    c.execute('UPDATE starboard_entries SET revision=revision+1,updated_at=%s WHERE id=%s',(now,entry['id']))
                    self._queue(c,entry['id'],now)
            self._audit(c,board,actor,event,now,{'revision':row['revision']})
            return {**row,'config':config}

    def observe(self,guild,board,revision,source,score):
        """The caller serializes source fetches; stale board fetches cannot write."""
        score=integer(score,'score',0,5000);now=int(self.clock())
        if source['guild_id']!=guild:raise PermissionError('source_guild_mismatch')
        with transaction(self.database_url) as c:
            self._enabled(c,guild);current=self._board(c,guild,board,locked=True)
            if current['revision']!=revision:raise RuntimeError('revision_conflict')
            config=current['config']
            if not config['enabled']:return None
            row=c.execute('SELECT * FROM starboard_entries WHERE board_id=%s AND source_message_id=%s FOR UPDATE',(board,source['message_id'])).fetchone()
            desired=eligible(config,source) and score>=config['threshold']
            if not row and not desired:return None
            snapshot=json.dumps(source,sort_keys=True,ensure_ascii=False)
            if row:
                if row['expires_at']<=now:return None
                if row['snapshot_json']==snapshot and row['score']==score and bool(row['desired'])==desired:return row
                row=c.execute('UPDATE starboard_entries SET snapshot_json=%s,score=%s,desired=%s,revision=revision+1,updated_at=%s WHERE id=%s RETURNING *',(snapshot,score,int(desired),now,row['id'])).fetchone()
            else:
                if c.execute('SELECT count(*) AS n FROM starboard_entries WHERE board_id=%s AND expires_at>%s',(board,now)).fetchone()['n']>=1000:raise ValueError('entry_limit')
                row=c.execute('INSERT INTO starboard_entries(board_id,guild_id,source_channel_id,source_message_id,snapshot_json,score,desired,created_at,updated_at,expires_at) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *',(board,guild,source['channel_id'],source['message_id'],snapshot,score,int(desired),now,now,now+config['retention_days']*86400)).fetchone()
            self._audit(c,board,0,'source_observed',now,{'score':score,'desired':desired},row['id'])
            self._queue(c,row['id'],now)
            return row

    def entries(self,guild,board,*,before=None,limit=50):
        with transaction(self.database_url) as c:
            self._board(c,guild,board)
            rows=c.execute('SELECT * FROM starboard_entries WHERE guild_id=%s AND board_id=%s AND expires_at>%s AND (%s::bigint IS NULL OR id<%s) ORDER BY id DESC LIMIT %s',(guild,board,int(self.clock()),before,before,max(1,min(100,limit)))).fetchall()
            return [{**r,'snapshot':json.loads(r['snapshot_json'])} for r in rows]

    def history(self,guild,board):
        with transaction(self.database_url) as c:
            self._board(c,guild,board)
            return [{**r,'detail':json.loads(r['detail_json'])} for r in c.execute('SELECT v.* FROM starboard_events v LEFT JOIN starboard_entries e ON e.id=v.entry_id WHERE v.board_id=%s AND (v.entry_id IS NULL OR e.expires_at>%s) ORDER BY v.id DESC LIMIT 100',(board,int(self.clock()))).fetchall()]

    def delivery_history(self,guild,board):
        with transaction(self.database_url) as c:
            self._board(c,guild,board);now=int(self.clock())
            jobs=c.execute('SELECT j.id,j.entry_id,j.status,j.attempts,j.last_error FROM starboard_outbox j JOIN starboard_entries e ON e.id=j.entry_id WHERE e.guild_id=%s AND e.board_id=%s AND e.expires_at>%s ORDER BY j.id DESC LIMIT 100',(guild,board,now)).fetchall()
            publications=c.execute('SELECT p.* FROM starboard_publications p JOIN starboard_entries e ON e.id=p.entry_id WHERE e.guild_id=%s AND e.board_id=%s AND e.expires_at>%s ORDER BY p.id DESC LIMIT 100',(guild,board,now)).fetchall()
            sources=c.execute('SELECT id,channel_id,message_id,status,attempts,last_error,retry_actor_id,retry_at FROM starboard_refresh_jobs WHERE guild_id=%s AND created_at>%s ORDER BY id DESC LIMIT 100',(guild,now-86400)).fetchall()
        return {'events':self.history(guild,board),'delivery':jobs,'publications':publications,'source_fetches':sources}

    def retry_source(self,guild,board,job_id,actor,revision):
        now=int(self.clock())
        with transaction(self.database_url) as c:
            self._enabled(c,guild);current=self._board(c,guild,board,locked=True)
            if type(revision) is not int or current['revision']!=revision:raise RuntimeError('revision_conflict')
            changed=c.execute("UPDATE starboard_refresh_jobs SET status='pending',attempts=0,available_at=%s,completed_at=NULL,last_error=NULL,retry_actor_id=%s,retry_at=%s WHERE id=%s AND guild_id=%s AND status='failed' AND lease_owner IS NULL AND created_at>%s",(now,actor,now,job_id,guild,now-86400)).rowcount
            if changed!=1:raise RuntimeError('source_not_retryable')
            self._audit(c,board,actor,'source_retry',now,{'job_id':job_id})

    def purge_expired(self):
        now=int(self.clock())
        with transaction(self.database_url) as c:
            # Source/history/jobs expire together, including disabled Guilds.
            return c.execute('DELETE FROM starboard_entries WHERE id IN (SELECT e.id FROM starboard_entries e WHERE e.expires_at<=%s AND NOT EXISTS(SELECT 1 FROM starboard_outbox j WHERE j.entry_id=e.id AND j.lease_until>%s) ORDER BY e.expires_at LIMIT 500 FOR UPDATE SKIP LOCKED)',(now,now)).rowcount

    def _owned(self,c,job):
        entry=c.execute('SELECT * FROM starboard_entries WHERE id=%s FOR UPDATE',(job['entry_id'],)).fetchone()
        lease=job['_lease']
        owned=c.execute("SELECT 1 FROM starboard_outbox WHERE id=%s AND entry_id=%s AND status='processing' AND lease_owner=%s AND lease_token=%s AND lease_until>%s FOR UPDATE",(job['id'],job['entry_id'],lease['owner'],lease['token'],int(self.clock()))).fetchone()
        if not entry or not owned:raise LostLease('Highlight delivery ownership changed')
        return entry

    def delivery_plan(self,job):
        with transaction(self.database_url) as c:
            parent=c.execute('SELECT guild_id,board_id FROM starboard_entries WHERE id=%s',(job['entry_id'],)).fetchone()
            if not parent:raise LostLease('Highlight no longer exists')
            self._enabled(c,parent['guild_id'])
            board=self._board(c,parent['guild_id'],parent['board_id'],locked=True)
            entry=self._owned(c,job);snapshot=json.loads(entry['snapshot_json']);config=board['config']
            desired=(entry['expires_at']>int(self.clock()) and config['enabled'] and eligible(config,snapshot) and entry['score']>=config['threshold'])
            publications=c.execute('SELECT * FROM starboard_publications WHERE entry_id=%s AND removed=0 ORDER BY id',(entry['id'],)).fetchall()
            return {'entry':entry,'source':snapshot,'config':config,'board_revision':board['revision'],'desired':desired,'publications':publications}

    def publication_begin(self,job,target):
        now=int(self.clock())
        with transaction(self.database_url) as c:
            self._owned(c,job)
            publication=c.execute('SELECT * FROM starboard_publications WHERE entry_id=%s AND target_channel_id=%s AND removed=0 FOR UPDATE',(job['entry_id'],target)).fetchone()
            if not publication:
                publication=c.execute('INSERT INTO starboard_publications(entry_id,target_channel_id,created_at) VALUES(%s,%s,%s) RETURNING *',(job['entry_id'],target,now)).fetchone()
            action='edit' if publication['message_id'] else 'recover' if publication['delivery_started'] else 'send'
            c.execute('UPDATE starboard_publications SET delivery_started=1 WHERE id=%s',(publication['id'],))
            return publication,action

    def publication_receipt(self,job,publication,receipt):
        with transaction(self.database_url) as c:
            entry=self._owned(c,job)
            changed=c.execute('UPDATE starboard_publications SET message_id=%s WHERE id=%s AND entry_id=%s AND removed=0 AND (message_id IS NULL OR message_id=%s)',(receipt,publication,entry['id'],receipt)).rowcount
            if changed!=1:raise LostLease('Highlight receipt changed')
            self._audit(c,entry['board_id'],0,'highlight_received',int(self.clock()),{'publication_id':publication,'message_id':receipt},entry['id'])

    def publication_not_sent(self,job,publication):
        """Only a definitive adapter rejection permits a future fresh send."""
        with transaction(self.database_url) as c:
            self._owned(c,job)
            c.execute('UPDATE starboard_publications SET delivery_started=0 WHERE id=%s AND entry_id=%s AND message_id IS NULL AND removed=0',(publication,job['entry_id']))

    def publication_removed(self,job,publication):
        with transaction(self.database_url) as c:
            entry=self._owned(c,job)
            changed=c.execute('UPDATE starboard_publications SET removed=1 WHERE id=%s AND entry_id=%s AND removed=0',(publication,entry['id'])).rowcount
            if changed:self._audit(c,entry['board_id'],0,'highlight_removed',int(self.clock()),{'publication_id':publication},entry['id'])

    def delivery_settled(self,job,revision):
        with transaction(self.database_url) as c:
            entry=self._owned(c,job)
            if entry['revision']!=revision:self._queue(c,entry['id'],int(self.clock()),except_job=job['id'])

    def retry(self,guild,board,job_id,actor,revision):
        now=int(self.clock())
        with transaction(self.database_url) as c:
            self._enabled(c,guild);current=self._board(c,guild,board,locked=True)
            if type(revision) is not int or current['revision']!=revision:raise RuntimeError('revision_conflict')
            entry=c.execute('SELECT e.* FROM starboard_entries e JOIN starboard_outbox j ON j.entry_id=e.id WHERE j.id=%s AND e.guild_id=%s AND e.board_id=%s AND e.expires_at>%s FOR UPDATE OF e',(job_id,guild,board,now)).fetchone()
            if not entry:raise LookupError('delivery_not_found')
            changed=c.execute("UPDATE starboard_outbox SET status='pending',attempts=0,available_at=%s,completed_at=NULL,last_error=NULL WHERE id=%s AND status='failed' AND lease_owner IS NULL",(now,job_id)).rowcount
            if changed!=1:raise RuntimeError('delivery_not_retryable')
            self._audit(c,board,actor,'delivery_retry',now,{'job_id':job_id},entry['id'])

    def delete_source(self,guild,channel,message_ids):
        """Keep tombstones even while disabled; delivery still obeys module OFF."""
        now=int(self.clock())
        with transaction(self.database_url) as c:
            rows=c.execute('SELECT * FROM starboard_entries WHERE guild_id=%s AND source_channel_id=%s AND source_message_id=ANY(%s) AND expires_at>%s ORDER BY id FOR UPDATE',(guild,channel,list(message_ids),now)).fetchall()
            return self._mark_deleted(c,rows,now)

    def delete_channel(self,guild,channel):
        now=int(self.clock())
        with transaction(self.database_url) as c:
            rows=c.execute("SELECT * FROM starboard_entries WHERE guild_id=%s AND (source_channel_id=%s OR snapshot_json::jsonb->>'parent_channel_id'=%s) AND expires_at>%s ORDER BY id FOR UPDATE",(guild,channel,str(channel),now)).fetchall()
            return self._mark_deleted(c,rows,now)

    def _mark_deleted(self,c,rows,now):
        count=0
        for row in rows:
            source=json.loads(row['snapshot_json'])
            if source.get('deleted'):continue
            source.update(deleted=True,content='',image_url='',author_name='')
            c.execute('UPDATE starboard_entries SET snapshot_json=%s,desired=0,revision=revision+1,updated_at=%s WHERE id=%s',(json.dumps(source,sort_keys=True,ensure_ascii=False),now,row['id']))
            self._audit(c,row['board_id'],0,'source_deleted',now,entry=row['id']);self._queue(c,row['id'],now);count+=1
        return count
