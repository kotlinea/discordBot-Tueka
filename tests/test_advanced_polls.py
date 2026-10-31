"""AP-INPUT/PRIVACY/VOTE/RACE: poll contracts against real PostgreSQL."""
import unittest
import tempfile
from pathlib import Path
import psycopg
from copy import deepcopy
from database import transaction
from database.testing import temporary_database
from engagement.polls.models import PollError, normalize, policy, duration, disclose
from poll_support import PublishedPollRepository as PollRepository
from concurrent.futures import ThreadPoolExecutor
from engagement.polls.models import Actor
from database.migrations import MIGRATIONS,apply


class PollRulesTests(unittest.TestCase):
    def test_duration_boundaries(self):
        self.assertEqual(duration('1d 3h 15m'), 98100)
        self.assertEqual(duration('30d'), 2592000)
        for value in ('0s', '31d', '-1h', '1h 1h', '1.5h', '1h junk', ''):
            with self.subTest(value=value), self.assertRaises(PollError):
                duration(value)

    def test_maximum_input_and_select(self):
        config = normalize(dict(question='問'*1024, description='説'*2000, options=[str(i)+'択'*253 for i in range(25)], max_choices=20))
        self.assertEqual(config['ui'], 'select')
        for changes in (dict(question='x'*1025), dict(options=['only one']), dict(max_choices=21), dict(image_url='file:///secret')):
            with self.subTest(changes=changes), self.assertRaises(PollError):
                normalize(dict(question='Q', options=['A', 'B'], **changes) if 'question' not in changes and 'options' not in changes else {'question': 'Q', 'options': ['A','B'], **changes})

    def test_policy_inclusion(self):
        with self.assertRaises(PollError):
            policy('custom', {'open': {'ballots':'everyone'}, 'closed': {}})

    def test_disclosure_matrix(self):
        for mode in ('public','anonymous','secret_winner','reveal_at_end','blind'):
            for status in ('open','closed'):
                for admin in (False,True):
                    poll = dict(id=1,status=status,config=normalize(dict(question='Q',options=['A','B'],mode=mode)),counts=[1,0],weighted_counts=[3,0],total=1,ballots=[dict(user_id=999,choices=[0],weight=3)])
                    result = disclose(poll,admin=admin,view_votes=admin)
                    if mode in ('anonymous','blind') or (status=='open' and mode in ('secret_winner','reveal_at_end')):
                        self.assertNotIn('ballots',result)
                    if status=='open' and mode in ('secret_winner','reveal_at_end','blind'):
                        self.assertNotIn('counts',result)
                        self.assertNotIn('total',result)
                    self.assertNotIn('creator_id',result)


class PollStorageTests(unittest.TestCase):
    def setUp(self):
        ctx=temporary_database()
        self.url=ctx.__enter__()
        self.addCleanup(ctx.__exit__,None,None,None)
        self.now=1000000
        self.repo=PollRepository(self.url,clock=lambda:self.now)
        self.repo.settings.set_module(1,'advanced_polls',enabled=True)
        self.repo.legacy_create(100,1,10,20,'Q',['A','B'],None,None)
        self.item=self.repo.by_message(100)

    def cast(self,user=30,choices=None,**kw):
        if 'revision' not in kw:kw['revision']=self.repo.get(1,self.item['id'])['revision']
        return self.repo.vote(1,self.item['id'],user,[0] if choices is None else choices,**kw)

    def test_replace_and_cancel(self):
        self.assertEqual(self.cast()['counts'],[1,0])
        self.assertEqual(self.cast(choices=[1])['counts'],[0,1])
        self.assertEqual(self.cast(choices=[])['total'],0)
        self.assertTrue(self.repo.get(1,self.item['id'])['ever_voted'])

    def test_multiple_weights_are_snapshots(self):
        self.repo.settings.set_module(1,'advanced_polls',enabled=True,settings={'role_weights':{'3':2,'4':10}})
        config={**self.item['config'],'max_choices':2}
        self.repo.edit(1,self.item['id'],20,config,1)
        result=self.cast(choices=[0,1],roles=[3,4])
        self.assertEqual(result['weighted_counts'],[10,10])
        self.assertEqual(self.repo.get(1,self.item['id'])['weighted_counts'],[10,10])
        result=self.cast(choices=[1],roles=[3])
        self.assertEqual(result['weighted_counts'],[0,2])

    def test_role_and_user_denials(self):
        config={**self.item['config'],'allowed_roles':['3'],'denied_users':['31']}
        self.repo.edit(1,self.item['id'],20,config,1)
        for user,roles in ((30,[]),(31,[3])):
            with self.assertRaises(PollError): self.cast(user,roles=roles)
        self.assertEqual(self.cast(30,roles=[3])['total'],1)

    def test_privacy_cannot_expand_after_cancel(self):
        self.cast()
        self.cast(choices=[])
        for config in ({**self.item['config'],'mode':'public'}, {**self.item['config'],'question':'Changed'}):
            with self.assertRaises(PollError): self.repo.edit(1,self.item['id'],20,config,1)

    def test_deadline_equal_rejected(self):
        with transaction(self.url) as c:
            c.execute('UPDATE polls SET closes_at=%s WHERE message_id=100',(self.now,))
        with self.assertRaises(PollError): self.cast()
        self.assertEqual(len(self.repo.close_expired()),1)

    def test_closed_poll_cosmetics_preserve_expired_deadline(self):
        with transaction(self.url) as c:c.execute('UPDATE polls SET closes_at=%s WHERE id=%s',(self.now,self.item['id']))
        self.repo.close_expired()
        item=self.repo.get(1,self.item['id'])
        edited=self.repo.edit(1,item['id'],20,{**item['config'],'color':0xffffff},item['revision'])
        self.assertEqual(edited['closes_at'],self.now)
        self.assertEqual(edited['config']['color'],0xffffff)

    def test_rescheduling_revalidates_a_retained_deadline(self):
        day=86400
        cases=((day,2*day,3*day,False),(day,2*day,2*day,False),
               (day,2*day,day+3600,True),(40*day,41*day,11*day,True),
               (40*day,41*day,11*day-1,False),(40*day,41*day,41*day-1,True),
               (40*day,41*day,None,False),(day,2*day,None,True),
               (None,2*day,3*day,False),(None,2*day,2*day,False),
               (None,2*day,day,True),(day,None,3*day,True))
        for index,(start,deadline,new_start,valid) in enumerate(cases):
            for explicit_deadline in (False,True):
                with self.subTest(start=start,deadline=deadline,new_start=new_start,explicit_deadline=explicit_deadline):
                    item=self.repo.create(1,10,20,dict(question='Scheduled',options=['A','B']),
                        f'reschedule-{index}-{explicit_deadline}',scheduled_at=self.now+start if start is not None else None,
                        closes_at=self.now+deadline if deadline is not None else None)
                    timing={'scheduled_at':self.now+new_start if new_start is not None else None}
                    if explicit_deadline:timing['closes_at']=item['closes_at']
                    if valid:
                        edited=self.repo.edit(1,item['id'],20,item['config'],item['revision'],**timing)
                        self.assertEqual(edited['scheduled_at'],timing['scheduled_at'])
                        self.assertEqual(edited['closes_at'],item['closes_at'])
                    else:
                        history=self.repo.history(1,item['id'])
                        with self.assertRaises(PollError) as error:
                            self.repo.edit(1,item['id'],20,item['config'],item['revision'],**timing)
                        self.assertEqual(error.exception.code,'invalid')
                        saved=self.repo.get(1,item['id'])
                        for field in ('scheduled_at','closes_at','revision','status'):
                            self.assertEqual(saved[field],item[field])
                        self.assertEqual(self.repo.history(1,item['id']),history)

    def test_participant_cap_closes_atomically(self):
        self.repo.edit(1,self.item['id'],20,{**self.item['config'],'max_participants':1},1)
        self.assertEqual(self.cast()['status'],'closed')
        with self.assertRaises(PollError): self.cast(31)
        self.assertEqual(self.repo.get(1,self.item['id'])['total'],1)

    def test_disabled_and_wrong_guild(self):
        self.repo.settings.set_module(1,'advanced_polls',enabled=False)
        with self.assertRaises(PollError): self.cast()
        with self.assertRaises(PollError): self.repo.get(2,self.item['id'])

    def test_revision_and_close_reopen_preserve_votes(self):
        self.cast()
        closed=self.repo.transition(1,self.item['id'],20,'close',1)
        with self.assertRaises(PollError): self.repo.transition(1,self.item['id'],20,'reopen',1)
        opened=self.repo.transition(1,self.item['id'],20,'reopen',closed['revision'],closes_at=self.now+10)
        self.assertEqual(opened['counts'],[1,0])
        self.assertEqual(opened['status'],'open')

    def test_creation_key(self):
        values=dict(question='New',options=['A','B'])
        first=self.repo.create(1,10,20,values,'unique')
        self.assertEqual(self.repo.create(1,10,20,values,'unique')['id'],first['id'])
        with self.assertRaises(PollError): self.repo.create(1,10,21,values,'unique')

    def test_unpublished_content_is_not_visible_to_members(self):
        item=self.repo.create(1,10,20,dict(question='Private draft',options=['A','B']),'private-draft')
        with self.assertRaises(PollError):self.repo.read(Actor(1,30),item['id'])
        self.assertEqual(self.repo.read(Actor(1,20,manager=True),item['id'])['config']['question'],'Private draft')

    def test_concurrent_participant_limit_has_one_winner(self):
        self.repo.edit(1,self.item['id'],20,{**self.item['config'],'max_participants':1},1)
        def vote(user):
            try:return self.cast(user)['status']
            except PollError:return 'rejected'
        with ThreadPoolExecutor(max_workers=2) as workers:
            result=list(workers.map(vote,[30,31]))
        self.assertCountEqual(result,['closed','rejected'])
        self.assertEqual(self.repo.get(1,self.item['id'])['total'],1)

    def test_revoked_delegation_rechecked_at_commit(self):
        principal=Actor(1,30,(3,))
        self.repo.settings.set_module(1,'advanced_polls',enabled=True,settings={'role_permissions':{'3':['manage']}})
        self.repo.settings.set_module(1,'advanced_polls',enabled=True,settings={'role_permissions':{}})
        with self.assertRaises(PollError):
            self.repo.edit(1,self.item['id'],30,self.item['config'],1,principal=principal)

    def test_stale_revision_cannot_withdraw_an_existing_vote(self):
        self.cast()
        edited=self.repo.edit(1,self.item['id'],20,{**self.item['config'],'color':0xffffff},self.item['revision'])
        with self.assertRaises(PollError) as error:self.cast(choices=[],revision=self.item['revision'])
        self.assertEqual(error.exception.code,'conflict')
        self.assertEqual(self.repo.get(1,self.item['id'])['counts'],[1,0])
        self.assertEqual(self.cast(choices=[],revision=edited['revision'])['total'],0)

    def test_vote_rechecks_revision_after_waiting_for_the_poll_lock(self):
        import json
        from threading import Event
        from unittest.mock import patch
        entered=Event()
        original=self.repo._row
        def row(*args,**kwargs):
            if kwargs.get('locked'):entered.set()
            return original(*args,**kwargs)
        with ThreadPoolExecutor(max_workers=1) as workers,patch.object(self.repo,'_row',row):
            with transaction(self.url) as c:
                c.execute('SELECT id FROM polls WHERE id=%s FOR UPDATE',(self.item['id'],))
                config={**self.item['config'],'options':['B','A']}
                c.execute('UPDATE polls SET revision=revision+1,config_json=%s,options_json=%s WHERE id=%s',
                          (json.dumps(config),json.dumps(config['options']),self.item['id']))
                future=workers.submit(self.repo.vote,1,self.item['id'],30,[0],message_id=100,revision=self.item['revision'])
                self.assertTrue(entered.wait(5))
                self.assertFalse(future.done())
            with self.assertRaises(PollError) as error:future.result(timeout=5)
            self.assertEqual(error.exception.code,'conflict')
        self.assertEqual(self.repo.get(1,self.item['id'])['counts'],[0,0])


class PollPayloadTests(unittest.IsolatedAsyncioTestCase):
    async def test_full_length_options_are_available_within_discord_budgets(self):
        from engagement.polls.discord_adapter import embed_for,public_view
        config=normalize(dict(question='Q'*1024,description='D'*2000,options=[str(i)+'X'*253 for i in range(25)]))
        result=dict(config=config,status='open',counts=[100]*25,weighted_counts=[10000]*25,ranking=[1]*25)
        recovered=''
        for page in range(5):
            embed=embed_for(result,page=page)
            self.assertLessEqual(len(embed),6000)
            self.assertTrue(all(len(field.value)<=1024 for field in embed.fields))
            recovered+='\n'.join(field.value for field in embed.fields)
        for option in config['options']:self.assertIn(option,recovered)
        view=public_view(100,config)
        self.assertLessEqual(len(view.children),25)

    async def test_builder_and_ballot_controls_fit_supported_components(self):
        from cogs.engagement.poll_builder import BuilderView
        from cogs.engagement.advanced_polls import BallotView
        from types import SimpleNamespace as NS
        config=normalize(dict(question='Q',options=[str(i) for i in range(25)],max_choices=20,allowed_roles=['3']))
        poll=dict(id=1,message_id=100,config=config,status='draft',counts=[0]*25,weighted_counts=[0]*25,total=0,ballots=[])
        builder=BuilderView(NS(),Actor(1,20,manager=True),poll)
        self.assertLessEqual(len(builder.children),25)
        self.assertEqual(len(builder.children[0].options),25)
        ballot=BallotView(NS(),Actor(1,20),poll)
        self.assertEqual(ballot.children[0].max_values,20)


class PollBuilderPreviewTests(unittest.IsolatedAsyncioTestCase):
    def builder(self, *, mode='anonymous', editing=False, visibility=None):
        from cogs.engagement.poll_builder import BuilderView
        from types import SimpleNamespace
        config=normalize(dict(question='Q',options=['A','B'],mode=mode,visibility=visibility))
        poll=dict(id=1,message_id=100,config=config,status='open' if editing else 'draft',
                  counts=[1,1] if editing else [0,0],weighted_counts=[7,3] if editing else [0,0],
                  total=2 if editing else 0,ballots=[dict(user_id=30,choices=[0],weight=7),dict(user_id=40,choices=[1],weight=3)] if editing else [])
        return BuilderView(SimpleNamespace(),Actor(1,20,(3,)),poll,editing=editing)

    async def test_unsaved_public_mode_does_not_reveal_hidden_results(self):
        for mode in ('blind','reveal_at_end','secret_winner'):
            with self.subTest(mode=mode):
                builder=self.builder(mode=mode,editing=True)
                builder.values['mode']='public'
                fields=builder.preview().fields
                self.assertEqual([(field.name,field.value) for field in fields],[('選択肢','1. A\n2. B')])
                self.assertEqual(builder.poll['config']['mode'],mode)

    async def test_custom_preview_cannot_expand_saved_visibility(self):
        hidden={stage:{field:'admins' for field in ('counts','ranking','total','participants','ballots')} for stage in ('open','closed')}
        for status in ('open','closed'):
            with self.subTest(status=status):
                builder=self.builder(mode='custom',editing=True,visibility=hidden)
                builder.poll['status']=status
                builder.values['visibility']={stage:{field:'everyone' for field in hidden[stage]} for stage in hidden}
                self.assertEqual([(field.name,field.value) for field in builder.preview().fields],[('選択肢','1. A\n2. B')])

    async def test_add_and_remove_options_refresh_sized_draft_counts(self):
        from types import SimpleNamespace
        from unittest.mock import AsyncMock
        builder=self.builder()
        response=SimpleNamespace(edit_message=AsyncMock())
        interaction=SimpleNamespace(response=response)
        await builder.add(interaction)
        embed=response.edit_message.call_args.kwargs['embed']
        self.assertIn('3. 選択肢 3 — **0**票',embed.fields[0].value)
        self.assertEqual(embed.fields[-1].value,'0 / 0')
        self.assertEqual(builder.poll['counts'],[0,0])
        builder.selected=0
        await builder.remove(interaction)
        embed=response.edit_message.call_args.kwargs['embed']
        self.assertIn('1. B — **0**票',embed.fields[0].value)
        self.assertIn('2. 選択肢 3 — **0**票',embed.fields[0].value)

    async def test_changed_options_do_not_reassign_existing_results(self):
        builder=self.builder(mode='public',editing=True)
        builder.values['options']=['B','A','C']
        builder.values['emojis']=['','','']
        fields=builder.preview().fields
        self.assertIn('3. C — **0**票',fields[0].value)
        self.assertNotIn('重み',fields[0].value)
        self.assertEqual(fields[-1].value,'0 / 0')

    async def test_public_cosmetic_preview_preserves_results_and_can_hide_them(self):
        builder=self.builder(mode='public',editing=True)
        builder.values['color']=0x123456
        fields=builder.preview().fields
        self.assertIn('重み 7',fields[0].value)
        self.assertEqual(fields[-1].value,'2 / 2')
        builder.values['mode']='blind'
        self.assertEqual([(field.name,field.value) for field in builder.preview().fields],[('選択肢','1. A\n2. B')])


class PollBallotRevisionTests(unittest.IsolatedAsyncioTestCase):
    async def test_confirm_rejects_a_screen_from_before_an_edit(self):
        from cogs.engagement.advanced_polls import BallotView
        from engagement.polls.service import PollService
        from types import SimpleNamespace as NS
        from unittest.mock import AsyncMock
        for changes in ({'options':['B','A']},{'options':['A','C']},{'color':0xffffff}):
            with self.subTest(changes=changes),temporary_database() as url:
                repo=PollRepository(url)
                repo.legacy_create(100,1,10,20,'Q',['A','B'],None,None)
                poll=repo.by_message(100)
                actor=Actor(1,30)
                cog=NS(actor=AsyncMock(return_value=actor),service=PollService(repo),failure=AsyncMock(),_sync_poll=AsyncMock())
                view=BallotView(cog,actor,poll,[0])
                repo.edit(1,poll['id'],20,{**poll['config'],**changes},poll['revision'])
                interaction=NS(response=NS(defer=AsyncMock()),edit_original_response=AsyncMock())
                await view.children[-1].callback(interaction)
                self.assertEqual(repo.get(1,poll['id'])['counts'],[0,0])
                cog.failure.assert_awaited_once()
                self.assertEqual(cog.failure.await_args.args[1].code,'conflict')
                interaction.edit_original_response.assert_not_awaited()
                refreshed=BallotView(cog,actor,repo.get(1,poll['id']),[0])
                await refreshed.children[-1].callback(interaction)
                self.assertEqual(repo.get(1,poll['id'])['counts'],[1,0])
                interaction.edit_original_response.assert_awaited_once()


class PollMigrationTests(unittest.TestCase):
    def test_old_ballots_survive_failed_upgrade_then_successful_upgrade(self):
        with temporary_database(migrate=False) as url,tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            for path in MIGRATIONS.glob('*.sql'):
                if int(path.name[:4])<10:(root/path.name).write_bytes(path.read_bytes())
            apply(url,root)
            with transaction(url) as c:
                c.execute("INSERT INTO polls(message_id,guild_id,channel_id,creator_id,question,options_json,created_at) VALUES(100,1,10,20,'Q','[\"same\",\"same\"]',1)")
                c.execute('INSERT INTO poll_votes VALUES(100,30,1,1)')
            for path in MIGRATIONS.glob('*.sql'):(root/path.name).write_bytes(path.read_bytes())
            (root/'0012_fail.sql').write_text('INSERT INTO missing_poll_table VALUES(1);',encoding='utf-8')
            with self.assertRaises(psycopg.Error):apply(url,root)
            with transaction(url) as c:
                self.assertEqual(c.execute('SELECT count(*) AS n FROM poll_votes').fetchone()['n'],1)
                self.assertIsNone(c.execute("SELECT column_name FROM information_schema.columns WHERE table_schema=current_schema() AND table_name='polls' AND column_name='id'").fetchone())
            (root/'0012_fail.sql').unlink()
            apply(url,root)
            repo=PollRepository(url)
            poll=repo.by_message(100)
            self.assertEqual(poll['counts'],[0,1])
            self.assertEqual(poll['config']['mode'],'anonymous')
            self.assertEqual(poll['config']['options'],['same','same'])
            self.assertEqual(apply(url)['applied'],[])

