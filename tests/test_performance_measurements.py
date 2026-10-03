"""Opt-in local measurements; no timing thresholds or operational credentials."""
import asyncio
from contextlib import contextmanager
import json
import math
import os
from pathlib import Path
import statistics
import time
import unittest
from unittest.mock import patch

import psycopg
from community import CommunityRepository
from database import transaction
from database.testing import temporary_database
from dashboard.api.context import create_context
from dashboard.api.features import FeaturePresenter
from features.registry import FEATURES
from observability.repository import snapshot


@unittest.skipUnless(os.environ.get('TUEKA_PERFORMANCE_PHASE'), 'Opt-in performance measurement')
class PerformanceMeasurements(unittest.TestCase):
    def test_performance_measurements(self):
        phase = os.environ['TUEKA_PERFORMANCE_PHASE']
        if phase not in {'before', 'after'}:
            raise ValueError('TUEKA_PERFORMANCE_PHASE must be before or after')
        results = {'phase': phase, 'warmup': 5, 'repetitions': 40, 'workloads': {}}
        with temporary_database() as url:
            repository = CommunityRepository(url)
            context = create_context(url, None)
            presenter = FeaturePresenter(context)
            if phase == 'before' and hasattr(presenter, 'feature_payloads'):
                raise ValueError('Before measurements require the pre-optimization sources')
            for feature in FEATURES:
                context.guild_settings_repository.set_module(1, feature.id, enabled=False)

            def xp():
                if phase == 'before':
                    repository.get_user(1, 10)
                return repository.add_xp(1, 10, 5)

            def features():
                if hasattr(presenter, 'feature_payloads'):
                    return presenter.feature_payloads(1, FEATURES, 0)
                return [presenter.feature_payload(1, feature, 0) for feature in FEATURES]

            original_execute = psycopg.Connection.execute
            original_connection = repository._connection
            original_settings_connection = context.guild_settings_repository._connection
            counts = {'sql': 0, 'application_sql': 0, 'transactions': 0}

            def execute(connection, query, params=None, **kwargs):
                counts['sql'] += 1
                return original_execute(connection, query, params, **kwargs)

            class CountedConnection:
                def __init__(self, connection):
                    self.connection = connection

                def execute(self, *args, **kwargs):
                    counts['application_sql'] += 1
                    return self.connection.execute(*args, **kwargs)

            @contextmanager
            def counted(factory):
                counts['transactions'] += 1
                with factory() as connection:
                    yield CountedConnection(connection)

            def measure(operation, *, repository_counts=True):
                for _ in range(5):
                    operation()
                samples, sql_counts, application_sql_counts, transactions = [], [], [], []
                with patch.object(psycopg.Connection, 'execute', execute), \
                     patch.object(repository, '_connection', lambda: counted(original_connection)), \
                     patch.object(context.guild_settings_repository, '_connection', lambda: counted(original_settings_connection)):
                    for _ in range(40):
                        counts.update(sql=0, application_sql=0, transactions=0)
                        started = time.perf_counter()
                        operation()
                        samples.append((time.perf_counter() - started) * 1000)
                        sql_counts.append(counts['sql'])
                        application_sql_counts.append(counts['application_sql'])
                        transactions.append(counts['transactions'])
                return {'median_ms': statistics.median(samples), 'p95_ms': sorted(samples)[math.ceil(len(samples) * .95) - 1],
                        'sql_per_call': statistics.median(sql_counts),
                        'application_sql_per_call': statistics.median(application_sql_counts) if repository_counts else None,
                        'transactions_per_call': statistics.median(transactions) if repository_counts else None}

            results['workloads']['xp_award'] = measure(xp)
            results['workloads']['feature_list'] = measure(features)
            results['queues'] = []
            with transaction(url) as connection:
                connection.execute("""INSERT INTO suggestions(id,guild_id,channel_id,author_id,answers_json,created_at,updated_at)
                    VALUES(1,1,1,1,'{}',1,1)""")
            for size in (1000, 100000):
                with transaction(url) as connection:
                    connection.execute('TRUNCATE suggestion_outbox')
                    connection.execute("""INSERT INTO suggestion_outbox(suggestion_id,action,status,available_at,created_at,completed_at)
                        SELECT 1,'sync','completed',1,1,2 FROM generate_series(1,%s)""", (size,))
                    connection.execute("""INSERT INTO suggestion_outbox(suggestion_id,action,status,available_at,created_at)
                        SELECT 1,'sync','pending',1,1 FROM generate_series(1,10)""")
                    connection.execute('ANALYZE suggestion_outbox')
                captured = []

                def capture(connection, query, params=None, **kwargs):
                    if isinstance(query, str) and 'FROM suggestion_outbox' in query:
                        captured.append((query, params))
                    return original_execute(connection, query, params, **kwargs)

                with patch.object(psycopg.Connection, 'execute', capture):
                    snapshot(url)
                timing = measure(lambda: snapshot(url), repository_counts=False)
                query, params = captured[-1]
                with transaction(url) as connection:
                    plan = connection.execute('EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON) ' + query, params).fetchone()['QUERY PLAN']
                results['queues'].append({'completed': size, 'pending': 10, 'snapshot': timing, 'plan': plan})

            async def blocking_delay():
                delays = []
                async def ticker():
                    started = time.perf_counter()
                    await asyncio.sleep(.005)
                    delays.append(max(0, (time.perf_counter() - started - .005) * 1000))
                task = asyncio.create_task(ticker())
                await asyncio.sleep(0)
                with transaction(url) as connection:
                    connection.execute('SELECT pg_sleep(0.05)')
                await task
                return delays[0]

            results['synchronous_db_loop_delay_ms'] = asyncio.run(blocking_delay())
        output = Path(os.environ.get('TUEKA_TASK_OUTPUT', 'artifacts/performance'))
        output.mkdir(parents=True, exist_ok=True)
        (output / f'performance-{phase}.json').write_text(json.dumps(results, indent=2), encoding='utf-8')
        print(json.dumps({key: value for key, value in results.items() if key != 'queues'}))
