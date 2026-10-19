"""Real Discord modal controls with fake transport; no network credentials."""
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from datetime import datetime,timezone
from unittest.mock import AsyncMock
from applications.repository import ApplicationRepository
from guild_settings import GuildSettingsRepository
from cogs.community.applications import ApplicationModal
from db_support import prepare_database
from test_applications import definition


class ApplicationDiscordTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.url=prepare_database(Path(temp.name)/'discord',self.addCleanup)
        self.repo=ApplicationRepository(self.url)
        self.settings=GuildSettingsRepository(self.url)
        self.settings.set_module(1,'applications',enabled=True)
        self.form=self.repo.save_form(1,99,definition(required_role_ids=[20]))
        self.member=SimpleNamespace(id=10,roles=[SimpleNamespace(id=20)],created_at=datetime(2020,1,1,tzinfo=timezone.utc),joined_at=datetime(2020,1,1,tzinfo=timezone.utc))
        self.guild=SimpleNamespace(id=1,fetch_member=AsyncMock(return_value=self.member))
        self.interaction=SimpleNamespace(id=100,guild=self.guild,user=SimpleNamespace(id=10),response=SimpleNamespace(defer=AsyncMock()),followup=SimpleNamespace(send=AsyncMock()))

    async def submit(self):
        modal=ApplicationModal(SimpleNamespace(repository=self.repo),self.form)
        modal.inputs['why']._value='Generated modal answer'
        await modal.on_submit(self.interaction)

    async def test_modal_submits_privately_using_current_member_not_opening_cache(self):
        await self.submit()
        self.guild.fetch_member.assert_awaited_once_with(10)
        self.interaction.response.defer.assert_awaited_once_with(ephemeral=True,thinking=True)
        self.assertTrue(self.interaction.followup.send.await_args.kwargs['ephemeral'])
        self.assertEqual(self.repo.items(1)[0]['answers'],{'why':'Generated modal answer'})

    async def test_role_removed_after_opening_rejects_without_saving(self):
        self.member.roles=[]
        await self.submit()
        self.assertEqual(self.repo.items(1),[])
        self.assertTrue(self.interaction.followup.send.await_args.kwargs['ephemeral'])

    async def test_disabled_or_changed_form_between_open_and_submit_is_rechecked(self):
        self.repo.save_form(1,99,definition(),form_id=self.form['id'],revision=1)
        await self.submit()
        self.assertEqual(self.repo.items(1),[])
