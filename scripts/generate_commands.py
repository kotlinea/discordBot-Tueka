"""Verify the documented command contract against an offline real Bot tree."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import sys
import tempfile
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


async def registered():
    from database.testing import temporary_database
    from discord import app_commands
    from config import Settings
    from bot import TuekaBot
    system = {key: os.environ[key] for key in ('TEMP', 'TMP', 'TMPDIR', 'SystemRoot', 'PATH') if key in os.environ}
    with tempfile.TemporaryDirectory() as scratch, temporary_database() as url, patch.dict(
        os.environ, {**system, 'DATABASE_URL': url, 'DISCORD_TOKEN': 'offline-command-docs', 'DATA_DIR': scratch}, clear=True
    ), patch('observability.heartbeat.state_path', return_value=Path(scratch) / 'bot-health.json'):
        async with TuekaBot(Settings.from_env()) as bot:
            with patch.object(bot.tree, 'sync', AsyncMock(return_value=[])):
                await bot.setup_hook()
            return {command.qualified_name: {
                'description': command.description,
                'parameters': [{'name': p.name, 'description': p.description, 'required': p.required,
                                'type': p.type.name, 'choices': [c.value for c in p.choices],
                                'default': None if p.required else p.default,
                                'min': p.min_value, 'max': p.max_value} for p in command.parameters],
                'module': command.callback.__module__,
            } for command in bot.tree.walk_commands() if isinstance(command, app_commands.Command)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    parser.add_argument('--write', action='store_true', help='Refresh contracts and pages; require existing bilingual descriptions')
    args = parser.parse_args()
    actual = asyncio.run(registered())
    path = ROOT / 'docs/reference/commands.json'
    if args.write:
        catalog = json.loads(path.read_text(encoding='utf-8'))
        if set(catalog) != set(actual):
            raise SystemExit('Add/remove entries and complete ja/en descriptions in docs/reference/commands.json before --write')
        for name in actual:
            catalog[name]['contract'] = actual[name]
            for lang in ('ja', 'en'):
                for field in ('usage', 'permissions', 'response', 'disabled', 'example'):
                    if not catalog[name][lang].get(field):
                        raise SystemExit(f'Missing {lang}/{field}: {name}')
        pages = {}
        for lang in ('ja', 'en'):
            page = ROOT / ('docs' if lang == 'ja' else 'docs/en') / 'reference/commands.md'
            prefix = page.read_text(encoding='utf-8').split('## /', 1)[0]
            pages[page] = prefix + '\n'.join(render_entry(name, entry, lang) for name, entry in catalog.items())
        path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        for page, text in pages.items():
            page.write_text(text, encoding='utf-8')
        print('Updated command contracts and bilingual pages')
    elif args.check:
        catalog = json.loads(path.read_text(encoding='utf-8'))
        if {k: v['contract'] for k, v in catalog.items()} != actual:
            raise SystemExit('Command contract changed; update bilingual commands.json and command pages')
        for name, value in catalog.items():
            for lang in ('ja', 'en'):
                for field in ('usage', 'permissions', 'response', 'disabled', 'example'):
                    if not value[lang].get(field):
                        raise SystemExit(f'Missing {lang}/{field}: {name}')
                page = ROOT / ('docs' if lang == 'ja' else 'docs/en') / 'reference/commands.md'
                if render_entry(name, value, lang) not in page.read_text(encoding='utf-8'):
                    raise SystemExit(f'Stale command page: {name}/{lang}')
        print(f'{len(actual)} commands: registration, arguments and bilingual pages match')
    else:
        print(json.dumps(actual, ensure_ascii=False, indent=2))


def render_entry(name, entry, lang):
    text = entry[lang]
    contract = entry['contract']
    params = ', '.join(p['name'] + ('*' if p['required'] else '') + ':' + p['type'] +
                       (f" ({', '.join(map(str, p['choices']))})" if p['choices'] else '') +
                       (f" [{p['min']}..{p['max']}]" if p.get('min') is not None or p.get('max') is not None else '') +
                       (f" = {json.dumps(p['default'], ensure_ascii=False)}" if not p['required'] and p.get('default') is not None else '')
                       for p in contract['parameters']) or '—'
    labels = ('用途', '引数（*必須）', '権限', '応答', '無効時', '例') if lang == 'ja' else ('Purpose', 'Arguments (* required)', 'Permissions', 'Response', 'When disabled', 'Example')
    values = (text['usage'], params, text['permissions'], text['response'], text['disabled'], '`/' + text['example'] + '`')
    return '## /' + name + '\n\n' + '\n'.join(f'- **{label}**: {value}' for label, value in zip(labels, values)) + '\n'


if __name__ == '__main__':
    main()
