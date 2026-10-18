"""Application workflow races, atomicity, privacy and retention on real PostgreSQL."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from database import transaction
from db_support import prepare_database
from guild_settings import GuildSettingsRepository
from applications.models import validate_form, can_submit
from applications.repository import ApplicationRepository


def definition(**changes):
    return {**dict(title='Staff',fields=[dict(key='why',label='Why?',style='paragraph',required=True,min_length=1,max_length=100)],enabled=True,cooldown_seconds=0),**changes}


class ApplicationsTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.url=prepare_database(Path(self.temp.name)/'app',self.addCleanup)
        self.repo=ApplicationRepository(self.url)
        self.settings=GuildSettingsRepository(self.url)
        self.settings.set_module(1,'applications',enabled=True)
        self.form=self.repo.save_form(1,900,definition())

    def submit(self,interaction=100,author=10,**changes):
        args=dict(revision=self.form['revision'],roles=[],created_at=1,joined_at=1)
        args.update(changes)
        return self.repo.submit(1,self.form['id'],author,interaction,{'why':'A generated test answer'},**args)

    def command_status(self, *, guild=1, author=10, withdraw_id=None):
        import asyncio
        from types import SimpleNamespace
        from unittest.mock import AsyncMock
        from cogs.community.applications import ApplicationsCog
        interaction = SimpleNamespace(guild=SimpleNamespace(id=guild), user=SimpleNamespace(id=author),
            response=SimpleNamespace(defer=AsyncMock()), followup=SimpleNamespace(send=AsyncMock()))
        asyncio.run(ApplicationsCog.status.callback(SimpleNamespace(repository=self.repo), interaction, withdraw_id))
        return interaction.followup.send.call_args

    def test_withdraw_by_id_reaches_pending_and_reviewing_beyond_latest_ten(self):
        oldest = self.submit()
        created = [oldest]
        for index in range(11):
            form = self.repo.save_form(1, 900, definition(title=f'Form {index}'))
            created.append(self.repo.submit(1, form['id'], 10, 101 + index, {'why': 'Generated'},
                revision=1, roles=[], created_at=1, joined_at=1))
        self.repo.transition(1, created[1]['id'], 900, 'reviewing', 'Generated review', revision=1)
        self.assertTrue(all(item['id'] not in {r['id'] for r in self.repo.items(1, author=10, limit=10)} for item in created[:2]))
        listing = self.command_status()
        self.assertEqual(len(listing.args[0].splitlines()), 10)
        self.assertTrue(listing.kwargs['ephemeral'])
        for item in created[:2]:
            with self.subTest(item_id=item['id']):
                reply = self.command_status(withdraw_id=item['id'])
                self.assertEqual(reply.args[0], '申請を取り下げました。')
                self.assertTrue(reply.kwargs['ephemeral'])
                self.assertEqual(self.repo.item(1, item['id'], author=10)['status'], 'withdrawn')
                self.assertEqual(self.repo.events(1, item['id'])[0]['actor_id'], 10)

    def test_withdraw_command_rejects_foreign_owner_guild_missing_and_expired(self):
        item = self.submit()
        for guild, author, item_id in ((1, 11, item['id']), (2, 10, item['id']), (1, 10, item['id'] + 1)):
            with self.subTest(guild=guild, author=author, item_id=item_id):
                reply = self.command_status(guild=guild, author=author, withdraw_id=item_id)
                self.assertEqual(reply.args[0], '取り下げられる申請が見つかりません。')
                self.assertTrue(reply.kwargs['ephemeral'])
        with transaction(self.url) as c:
            c.execute('UPDATE applications SET expires_at=0 WHERE id=%s', (item['id'],))
        self.assertEqual(self.command_status(withdraw_id=item['id']).args[0], '取り下げられる申請が見つかりません。')
        with transaction(self.url) as c:
            self.assertEqual(c.execute('SELECT status FROM applications WHERE id=%s', (item['id'],)).fetchone()['status'], 'pending')
            self.assertEqual(c.execute('SELECT COUNT(*) AS n FROM application_events WHERE application_id=%s', (item['id'],)).fetchone()['n'], 1)

    def test_submission_replay_snapshot_and_open_limit(self):
        item=self.submit()
        self.assertEqual(self.submit()['id'],item['id'])
        with self.assertRaisesRegex(RuntimeError,'open'):
            self.submit(101)
        self.repo.save_form(1,900,definition(title='Changed'),form_id=self.form['id'],revision=1)
        self.assertEqual(self.repo.items(1)[0]['snapshot']['title'],'Staff')
        self.assertEqual(len(self.repo.events(1,item['id'])),1)

    def test_changed_modal_disabled_form_and_module_reject_without_writes(self):
        self.repo.save_form(1,900,definition(),form_id=self.form['id'],revision=1)
        with self.assertRaisesRegex(RuntimeError,'changed'):
            self.submit()
        self.form=self.repo.save_form(1,900,{**definition(),'enabled':False},form_id=self.form['id'],revision=2)
        with self.assertRaises(PermissionError):self.submit()
        self.settings.set_module(1,'applications',enabled=False)
        with self.assertRaises(PermissionError):self.submit()
        self.assertEqual(self.repo.items(1),[])

    def test_access_policy_deny_priority_age_and_unknown_membership(self):
        form=validate_form(definition(required_role_ids=[20],denied_role_ids=[30],account_age_days=2,member_age_days=1))
        for roles,created,joined,expected in [([20],0,0,True),([],0,0,False),([20,30],0,0,False),([20],199999,0,False),([20],0,None,False)]:
            self.assertEqual(can_submit(form,roles,created_at=created,joined_at=joined,now=200000),expected)
        self.form=self.repo.save_form(1,900,form,form_id=self.form['id'],revision=1)
        with self.assertRaises(PermissionError):self.submit()
        self.assertEqual(self.repo.items(1),[])

    def test_answer_validation_unknown_missing_and_oversized(self):
        for answers in ({},{'why':' '},{'why':'x'*101},{'why':'ok','other':'extra'},{'why':123}):
            with self.assertRaises(ValueError):
                self.repo.submit(1,self.form['id'],10,100,answers,revision=1,roles=[],created_at=1,joined_at=1)
        self.assertEqual(self.repo.items(1),[])

    def test_review_reason_self_revision_final_state_and_audit(self):
        item=self.submit()
        with self.assertRaises(PermissionError):self.repo.transition(1,item['id'],10,'approved','Self',revision=1)
        with self.assertRaises(ValueError):self.repo.transition(1,item['id'],20,'approved',' ',revision=1)
        item=self.repo.transition(1,item['id'],20,'reviewing','Checking',revision=1)
        with self.assertRaises(RuntimeError):self.repo.transition(1,item['id'],20,'approved','Old',revision=1)
        item=self.repo.transition(1,item['id'],20,'approved','Complete',revision=item['revision'])
        with self.assertRaises(RuntimeError):self.repo.transition(1,item['id'],20,'rejected','Again',revision=item['revision'])
        self.assertEqual([e['event_type'] for e in self.repo.events(1,item['id'])],['approved','reviewing','submitted'])
        self.assertEqual(self.repo.events(1,item['id'])[0]['reason'],'Complete')

    def test_foreign_guild_and_withdrawal_ownership(self):
        item=self.submit()
        with self.assertRaises(LookupError):self.repo.form(2,self.form['id'])
        with self.assertRaises(LookupError):self.repo.events(2,item['id'])
        self.assertEqual(self.repo.items(2),[])
        self.assertEqual(self.repo.items(1,author=20),[])
        with self.assertRaises(PermissionError):self.repo.transition(1,item['id'],20,'withdrawn','',revision=1,withdraw=True)
        self.assertEqual(self.repo.transition(1,item['id'],10,'withdrawn','',revision=1,withdraw=True)['status'],'withdrawn')

    def test_disabling_pauses_review_but_keeps_read_and_retention(self):
        item=self.submit()
        self.settings.set_module(1,'applications',enabled=False)
        with self.assertRaises(PermissionError):self.repo.transition(1,item['id'],20,'approved','Good',revision=1)
        self.assertEqual(len(self.repo.items(1)),1)
        self.assertEqual(self.repo.purge_expired(now=item['expires_at']),1)
        self.assertEqual(self.repo.items(1),[])
        with transaction(self.url) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) AS n FROM application_events').fetchone()['n'],0)
            self.assertEqual(c.execute('SELECT COUNT(*) AS n FROM application_forms').fetchone()['n'],1)

    def test_expired_items_hidden_before_cleanup_and_new_intake_allowed(self):
        item=self.submit()
        with transaction(self.url) as c:
            c.execute('UPDATE applications SET expires_at=1 WHERE id=%s',(item['id'],))
        self.assertEqual(self.repo.items(1),[])
        with self.assertRaises(LookupError):self.repo.events(1,item['id'])
        self.assertNotEqual(self.submit(101)['id'],item['id'])

    def test_restart_preserves_pending_definition_history_and_expiry(self):
        item=self.submit()
        fresh=ApplicationRepository(self.url)
        self.assertEqual(fresh.form(1,self.form['id']),self.form)
        self.assertEqual(fresh.items(1)[0],item)
        self.assertEqual(fresh.events(1,item['id'])[0]['event_type'],'submitted')

    def test_concurrent_submission_only_one_and_replay_only_one(self):
        def call(interaction):
            try:return self.submit(interaction)['id']
            except RuntimeError:return None
        with ThreadPoolExecutor(2) as pool:result=list(pool.map(call,[100,101]))
        self.assertEqual(sum(v is not None for v in result),1)
        self.assertEqual(len(self.repo.items(1)),1)

    def test_concurrent_review_one_commits_and_audit_matches(self):
        item=self.submit()
        def review(status):
            try:return self.repo.transition(1,item['id'],20,status,'Decision',revision=1)['status']
            except RuntimeError:return None
        with ThreadPoolExecutor(2) as pool:result=list(pool.map(review,['approved','rejected']))
        self.assertEqual(sum(v is not None for v in result),1)
        self.assertEqual(len(self.repo.events(1,item['id'])),2)
        self.assertEqual(self.repo.events(1,item['id'])[0]['event_type'],self.repo.items(1)[0]['status'])

    def test_configuration_revision_and_audit_are_atomic(self):
        with self.assertRaises(RuntimeError):self.repo.save_form(1,900,definition(),form_id=self.form['id'],revision=0)
        with transaction(self.url) as c:
            self.assertEqual(c.execute('SELECT COUNT(*) AS n FROM application_form_events').fetchone()['n'],1)
        with self.assertRaises(LookupError):self.repo.save_form(2,900,definition(),form_id=self.form['id'],revision=1)

    def test_invalid_form_limits_and_repeated_keys(self):
        for value in [definition(title=''),definition(fields=[]),definition(fields=[{'key':'a','label':'A'}]*2),definition(retention_days=0),definition(required_role_ids=['-1']),definition(account_age_days=True)]:
            with self.assertRaises(ValueError):validate_form(value)

    def test_failed_audit_rolls_back_intake_and_review(self):
        @contextmanager
        def broken(url):
            with transaction(url) as connection:
                class AuditFailure:
                    def execute(self,query,*args,**kwargs):
                        if query.startswith('INSERT INTO application_events'):
                            raise RuntimeError('injected_audit_failure')
                        return connection.execute(query,*args,**kwargs)
                yield AuditFailure()
        with patch('applications.repository.transaction',broken):
            with self.assertRaisesRegex(RuntimeError,'injected'):
                self.submit()
        self.assertEqual(self.repo.items(1),[])
        item=self.submit()
        with patch('applications.repository.transaction',broken):
            with self.assertRaisesRegex(RuntimeError,'injected'):
                self.repo.transition(1,item['id'],20,'approved','Reason',revision=1)
        self.assertEqual(self.repo.items(1)[0]['status'],'pending')
        self.assertEqual(len(self.repo.events(1,item['id'])),1)
