"""Test-only implementation; never registered by the shipped application."""
from discord import app_commands
from fastapi import APIRouter, Depends
from dashboard.api.dependencies import ApiDependencies

events = []


async def setup(bot):
    events.append('setup')
    async def probe(interaction):
        pass
    bot.tree.add_command(app_commands.Command(name='g5_probe', description='Registration probe', callback=probe))


async def teardown(bot):
    events.append('teardown')


def create_router(context):
    events.append('router')
    auth = ApiDependencies(context.dashboard_repository, context.discord)
    router = APIRouter()
    @router.get('/guilds/{guild_id}/g5-probe')
    async def probe(guild_id: int, access=Depends(auth.read)):
        return {'guild_id': str(guild_id)}
    return router
