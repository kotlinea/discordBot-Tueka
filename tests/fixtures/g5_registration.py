"""Fresh-process registration acceptance: alter declarations only, then boot normally."""
import asyncio
from dataclasses import replace
import importlib
import os
from pathlib import Path
import sys
import tempfile
from contextlib import ExitStack
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'tests'))


async def main(mode):
    import features.registry as registrations
    from features.contracts import Binding, Category
    from features.community import registry as community
    original = registrations.REGISTRY
    probe = replace(original.by_id['welcome'], id='g5_probe', fields=(), required_fields=(),
        required_bot_permissions=(), docs_path='/docs/features/g5-probe', settings_factory=None,
        bindings=(Binding('g5_bot', 'bot', 'g5_extension:setup', 999),
                  Binding('g5_api', 'api', 'g5_extension:create_router', 999)))
    if mode == 'existing':
        community.CATEGORY = replace(community.CATEGORY, features=(*community.CATEGORY.features, probe))
        importlib.reload(registrations)
    elif mode == 'category':
        registrations.G5_CATEGORY = Category('g5_category', 'nav.g5', (replace(probe, category='g5_category'),))
        registrations.G5_BASE_CATEGORIES = original.categories
        # Evaluate the real registry with just its category registration line changed
        # in memory. Keep the production derivation of metadata/extensions intact.
        source = Path(registrations.__file__).read_text(encoding='utf-8')
        declaration, = [line for line in source.splitlines() if line.startswith('REGISTRY = Registry(')]
        source = source.replace(declaration, 'REGISTRY = Registry((*G5_BASE_CATEGORIES, G5_CATEGORY), CORE_BINDINGS)')
        exec(compile(source, registrations.__file__, 'exec'), registrations.__dict__)
    assert 'g5_extension' not in sys.modules, 'Metadata eagerly imported an implementation'

    # All production composition modules are imported after the declaration change.
    from api_support import ApiFixture
    from bot import TuekaBot
    from config import Settings
    present = mode != 'removed'
    assert ('g5_extension' in Settings.__dataclass_fields__['extensions'].default) == present
    with tempfile.TemporaryDirectory() as scratch, ExitStack() as cleanup:
        root = Path(scratch)
        api = ApiFixture(root, cleanup.callback)
        cleanup.callback(api.client.close)
        result = api.client.get('/api/v1/guilds/1/g5-probe')
        assert result.status_code == (200 if present else 404), result.text
        if present:
            api_extension = importlib.import_module('g5_extension')
            assert api_extension.events == ['router']
            assert result.json() == {'guild_id': '1'}
            api.discord.can_manage.return_value = False
            assert api.client.get('/api/v1/guilds/1/g5-probe').status_code == 403
            api.discord.can_manage.return_value = True
            metadata = api.client.get('/api/v1/guilds/1/overview').json()['features']
            expected_category = probe.category if mode == 'existing' else 'g5_category'
            assert next(item for item in metadata if item['id'] == 'g5_probe')['category'] == expected_category
            url = '/api/v1/guilds/1/modules/g5_probe'
            before = api.client.get(url).json()
            body = {'enabled': True, 'settings': {}, 'revision': before['revision']}
            saved = api.client.put(url, json=body, headers=api.headers)
            assert saved.status_code == 200, saved.text
            assert api.client.get(url).json()['enabled'] is True
            assert api.client.put(url, json=body, headers=api.headers).status_code == 409
            assert api.client.put(url, json=body).status_code == 403
        else:
            assert api.client.get('/api/v1/guilds/1/modules/g5_probe').status_code == 404
            assert 'g5_probe' not in registrations.FEATURE_BY_ID
        system = {key: os.environ[key] for key in ('PATH', 'TEMP', 'TMP', 'TMPDIR', 'SystemRoot') if key in os.environ}
        with patch.dict(os.environ, {**system, 'DATABASE_URL': api.database, 'DISCORD_TOKEN': 'offline-g5', 'DATA_DIR': scratch}, clear=True), \
             patch('observability.heartbeat.state_path', return_value=root / 'bot-health.json'):
            async with TuekaBot(Settings.from_env()) as bot:
                with patch.object(bot.tree, 'sync', AsyncMock(return_value=[])) as sync:
                    await asyncio.gather(bot.setup_hook(), bot.setup_hook())
                sync.assert_awaited_once()
                assert (bot.tree.get_command('g5_probe') is not None) == present
                assert bot.tree.get_command('help') is not None
                if present:
                    extension = importlib.import_module('g5_extension')
                    assert extension.events.count('setup') == 1
                    assert api_extension.events == ['router']
            if present:
                assert extension.events.count('teardown') == 1
                assert 'g5_extension' not in bot.extensions
            else:
                assert 'g5_extension' not in sys.modules
    print(f'{mode}: Bot/API/default settings registration and removal OK')


if __name__ == '__main__':
    asyncio.run(main(sys.argv[1]))
