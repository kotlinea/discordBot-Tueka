"""Read-only operational aggregates and narrowly scoped heartbeat writes."""
from contextlib import contextmanager
import json
import time

from database.connections import pool
from database.migrations import load
from jobs.catalog import QUEUE_SPECS

SERVICES = ('bot', 'dashboard', 'social-worker')


@contextmanager
def connection(url, *, write=False):
    with pool(url).connection(timeout=2) as client:
        with client.transaction():
            if not write:
                client.execute('SET TRANSACTION READ ONLY')
            client.execute("SET LOCAL statement_timeout = '2s'")
            client.execute("SET LOCAL lock_timeout = '1s'")
            yield client


def database_ready(url):
    with connection(url) as client:
        rows = client.execute('SELECT version,name,checksum FROM schema_migrations ORDER BY version').fetchall()
        return [(row['version'], row['name'], row['checksum']) for row in rows] == [row[:3] for row in load()]


def heartbeat(url, service, instance, ready, metrics):
    if service not in SERVICES:
        raise ValueError('Unknown service')
    with connection(url, write=True) as client:
        client.execute('''INSERT INTO runtime_heartbeats(service,instance_id,observed_at,ready,metrics_json)
            VALUES(%s,%s,extract(epoch from clock_timestamp())::double precision,%s,%s)
            ON CONFLICT(service,instance_id) DO UPDATE SET observed_at=excluded.observed_at,
            ready=excluded.ready,metrics_json=excluded.metrics_json''',
            (service, instance, bool(ready), json.dumps(metrics)))
        client.execute('DELETE FROM runtime_heartbeats WHERE observed_at<extract(epoch from clock_timestamp())-86400')


def snapshot(url, *, heartbeat_age=30, queue_age=300):
    with connection(url) as client:
        now = float(client.execute('SELECT extract(epoch from clock_timestamp()) AS now').fetchone()['now'])
        heartbeats = client.execute('''SELECT DISTINCT ON(service) service,observed_at,ready,metrics_json
            FROM runtime_heartbeats ORDER BY service,observed_at DESC,instance_id''').fetchall()
        services = {name: {'ready': False, 'age_seconds': -1, 'metrics': []} for name in SERVICES}
        for row in heartbeats:
            age = max(0, now - row['observed_at'])
            services[row['service']] = {'ready': bool(row['ready']) and age <= heartbeat_age,
                                       'age_seconds': age, 'metrics': json.loads(row['metrics_json'])}
        queues = {}
        for name, spec in QUEUE_SPECS.items():
            created = spec.created or spec.due
            row = client.execute(f'''SELECT
                COUNT(*) FILTER(WHERE {spec.state} IN ('pending','retry','processing')) AS active,
                COUNT(*) FILTER(WHERE {spec.state}='failed') AS failed,
                COUNT(*) FILTER(WHERE {spec.state}='retry') AS retry,
                COUNT(*) FILTER(WHERE {spec.state}='processing' AND lease_until<=%s) AS expired_leases,
                COALESCE(MAX(%s-GREATEST({spec.due},{created})) FILTER(WHERE {spec.state} IN ('pending','retry','processing') AND {spec.due}<=%s),0) AS oldest_due_age_seconds
                FROM {name}''', (now, now, now)).fetchone()
            queues[name] = {key: max(0, float(value)) for key, value in row.items()}
        activity = client.execute('''SELECT COUNT(*) AS connections,
            COUNT(*) FILTER(WHERE state='active') AS active_connections,
            COUNT(*) FILTER(WHERE wait_event_type='Lock' AND usename=current_user) AS lock_waiters,
            COALESCE(MAX(extract(epoch from clock_timestamp()-query_start))
                FILTER(WHERE wait_event_type='Lock' AND usename=current_user),0) AS oldest_lock_wait_seconds
            FROM pg_stat_activity WHERE datname=current_database()''').fetchone()
        stats = client.execute('''SELECT deadlocks AS deadlocks_total,xact_commit AS commits_total,xact_rollback AS rollbacks_total,
            COALESCE(extract(epoch from stats_reset),0) AS stats_reset_timestamp
            FROM pg_stat_database WHERE datname=current_database()''').fetchone()
    database = {key: float(value) for key, value in {**activity, **stats}.items()}
    alerts = ['service_unavailable:' + name for name, values in services.items() if not values['ready']]
    for name, values in queues.items():
        if values['failed']:
            alerts.append('dead_letter:' + name)
        if values['oldest_due_age_seconds'] > queue_age:
            alerts.append('queue_delayed:' + name)
        if values['expired_leases']:
            alerts.append('lease_expired:' + name)
    if database['lock_waiters']:
        alerts.append('database_lock_wait')
    return {'database': database, 'services': services, 'queues': queues, 'alerts': alerts,
            'thresholds': {'heartbeat_age_seconds': heartbeat_age, 'queue_age_seconds': queue_age}}
