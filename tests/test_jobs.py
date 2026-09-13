import asyncio
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from database import transaction
from db_support import prepare_database
from jobs import Claim, LostLease, Outcome, QueueRepository, QueueSpec, RetryJob, run_batch


QUEUES = (
    (QueueSpec('ticket_outbox'), "ticket_id,action,actor_id,payload_json,available_at,created_at", "1,'reply',2,'{}',0,1"),
    (QueueSpec('ticket_schedules', due='due_at'), "ticket_id,kind,due_at,created_at", "1,'inactivity',0,1"),
    (QueueSpec('reaction_role_outbox', state='state', due='next_attempt_at', done='done'), "guild_id,action,created_at", "1,'sync',1"),
    (QueueSpec('reaction_role_schedules', state='state', due='due_at', done='done'), "guild_id,kind,due_at,created_at", "1,'temp_role',0,1"),
    (QueueSpec('social_events', completed='processed_at'), "provider,event_key,account_id,payload_json,received_at", "'x','one','creator','{}',1"),
    (QueueSpec('moderation_action_requests', result='result_json'), "guild_id,moderator_id,action,created_at,dedupe_key", "1,2,'warn',1,'one'"),
    (QueueSpec('scheduled_moderation_actions', due='due_at'), "guild_id,user_id,action,due_at", "1,2,'unban',0"),
)


class QueueContracts(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = prepare_database(Path(self.temp.name) / 'jobs.db')
        self.now = 1000

    def seed(self, spec, columns, values):
        with transaction(self.path) as c:
            c.execute(f'INSERT INTO {spec.table}({columns}) VALUES({values})')
        return QueueRepository(self.path, spec, clock=lambda: self.now)

    def test_every_queue_fences_expired_and_same_owner_claims(self):
        for spec, columns, values in QUEUES:
            with self.subTest(queue=spec.table):
                store = self.seed(spec, columns, values)
                first = store.claim('same-owner', lease_seconds=3)
                self.assertIsNone(store.claim('other'))
                self.now += 3
                self.assertFalse(store.renew(first))
                self.assertFalse(store.finish(first, Outcome()))
                second = store.claim('same-owner')
                self.assertEqual(second.id, first.id)
                self.assertNotEqual(second.token, first.token)
                self.assertFalse(store.finish(first, Outcome('stale', retry=True)))
                self.assertTrue(store.renew(second))
                self.assertTrue(store.finish(second, Outcome(result={'done': True})))
                with transaction(self.path) as c:
                    self.assertEqual(c.execute(f'SELECT {spec.due} FROM {spec.table} WHERE id=?', (second.id,)).fetchone()[0], second.payload[spec.due])
                self.assertFalse(store.finish(second, Outcome()))
                self.assertIsNone(store.claim('other'))

    def test_every_queue_retries_then_dead_letters_and_retains_terminal_rows(self):
        for spec, columns, values in QUEUES:
            with self.subTest(queue=spec.table):
                store = self.seed(spec, columns, values)
                for attempt in range(1, spec.max_attempts + 1):
                    claim = store.claim('worker')
                    self.assertEqual(claim.attempt, attempt)
                    self.assertTrue(store.finish(claim, Outcome('temporary', retry=True)))
                    self.assertIsNone(store.claim('early'))
                    self.now += 4000
                self.assertIsNone(store.claim('after-limit'))
                self.assertEqual(store.purge(retention_seconds=10000), 0)
                self.now += 10000
                self.assertEqual(store.purge(retention_seconds=10000), 1)

    def test_crashed_final_attempt_terminates_and_live_attempt_is_not_purged(self):
        spec, columns, values = QUEUES[0]
        store = self.seed(spec, columns, values)
        for _ in range(spec.max_attempts):
            self.assertIsNotNone(store.claim('crashing', lease_seconds=3))
            self.assertEqual(store.purge(retention_seconds=1), 0)
            self.now += 3
        self.assertIsNone(store.claim('restart'))
        with transaction(self.path) as c:
            self.assertEqual(c.execute('SELECT status FROM ticket_outbox').fetchone()[0], 'failed')

    def test_parallel_claims_have_one_owner(self):
        store = self.seed(*QUEUES[0])
        with ThreadPoolExecutor(max_workers=4) as pool:
            claims = list(pool.map(lambda n: store.claim(str(n)), range(12)))
        self.assertEqual(sum(claim is not None for claim in claims), 1)


class MemoryStore:
    def __init__(self):
        self.claimed = False
        self.outcomes = []
        self.live = True

    def claim(self, owner, **kwargs):
        if self.claimed:
            return None
        self.claimed = True
        return Claim(1, owner, 'token', {'id': 1}, 1)

    def renew(self, claim, **kwargs):
        return self.live

    def purge(self, **kwargs):
        return 0

    def finish(self, claim, outcome):
        self.outcomes.append(outcome)
        return self.live


class RunnerContracts(unittest.IsolatedAsyncioTestCase):
    async def test_long_handler_is_renewed_before_acknowledgement(self):
        store, renewed = MemoryStore(), asyncio.Event()
        def renew(claim, **kwargs):
            renewed.set()
            return True
        store.renew = renew
        async def handler(payload):
            await asyncio.wait_for(renewed.wait(), timeout=3)
            return Outcome(result={'ok': True})
        self.assertEqual(await run_batch(store, 'worker', handler, lease_seconds=3), 1)
        self.assertEqual(store.outcomes, [Outcome(result={'ok': True})])

    async def test_retry_failure_is_classified_once(self):
        store = MemoryStore()
        async def handler(payload):
            raise RetryJob('later')
        self.assertEqual(await run_batch(store, 'worker', handler), 1)
        self.assertEqual(store.outcomes, [Outcome('later', retry=True)])

    async def test_cancellation_never_acknowledges_unfinished_work(self):
        store, started = MemoryStore(), asyncio.Event()
        async def handler(payload):
            started.set()
            await asyncio.Future()
        task = asyncio.create_task(run_batch(store, 'worker', handler))
        await started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        self.assertEqual(store.outcomes, [])

    async def test_lease_loss_cancels_handler_without_acknowledgement(self):
        store, stopped = MemoryStore(), asyncio.Event()
        store.live = False
        async def handler(payload):
            try:
                await asyncio.Future()
            finally:
                stopped.set()
        self.assertEqual(await run_batch(store, 'worker', handler, lease_seconds=3), 0)
        self.assertTrue(stopped.is_set())
        self.assertEqual(store.outcomes, [])
