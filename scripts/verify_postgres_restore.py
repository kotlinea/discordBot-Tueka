"""Destructive only to UUID databases created here on an explicit test server.

Runs real pg_dump/pg_restore. --client-container uses those binaries inside the
local test PostgreSQL container, without replacing their results with mocks.
"""
import argparse
from contextlib import nullcontext
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch
from urllib.parse import urlsplit, urlunsplit
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from psycopg import sql
from database import close_pools, connect, require_current, transaction
from database.migrations import apply
from database.operations import backup, inventory, restore
from database.testing import test_database_url
from suggestions import SuggestionRepository
from guild_settings import GuildSettingsRepository
from ticketing import TicketRepository


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--client-container')
    args = parser.parse_args()
    base = test_database_url()
    parts = urlsplit(base)
    if parts.query:
        raise ValueError('Restore verification requires a test database URL without schema options')
    original_run = subprocess.run

    def run_client(command, **options):
        env = options['env']
        docker = ['docker', 'exec', '-i']
        for key, value in env.items():
            if key.startswith('PG'):
                value = '127.0.0.1' if key == 'PGHOST' else '5432' if key == 'PGPORT' else value
                docker.extend(['-e', key + '=' + value])
        return original_run([*docker, args.client_container, *command], **options)

    suffix = uuid.uuid4().hex
    names = [f'tueka_test_restore_{suffix}_{kind}' for kind in ('source', 'target', 'invalid')]
    urls = [urlunsplit(parts._replace(path='/' + name)) for name in names]
    created = []
    try:
        with connect(base, autocommit=True) as admin:
            for name in names:
                admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
                created.append(name)
        source, target, invalid = urls
        apply(source)
        repo = SuggestionRepository(source)
        item = repo.create(1234567890123456789, 1234567890123456790, 1234567890123456791, {'idea': 'restore-proof'})
        repo.vote(1234567890123456789, item['id'], 1234567890123456792, 1)
        GuildSettingsRepository(source).set_module(1, 'welcome', enabled=True, settings={'welcome_channel_id': 100})
        tickets = TicketRepository(source)
        team = tickets.save_team(1, {'name': 'Staff', 'role_ids': [500]})
        panel = tickets.save_panel(1, {'name': 'Support', 'mode': 'channel', 'category_id': 100, 'team_id': team['id']})
        ticket = tickets.reserve_ticket(1, panel['id'], 10, 'restore', {})
        transcript = tickets.save_transcript(ticket['id'], 's3', 'encrypted-transcripts/proof', 'content-hash', 123, 9999999999)
        before = inventory(source)
        with tempfile.TemporaryDirectory(prefix='tueka-restore-') as directory:
            dump = Path(directory) / 'snapshot.dump'
            adapter = patch('database.operations.subprocess.run', side_effect=run_client) if args.client_container else nullcontext()
            with adapter:
                result = backup(source, dump)
                assert dump.read_bytes()[:5] == b'PGDMP'
                restore(dump, target)
                require_current(target)
                assert inventory(target) == before
                assert GuildSettingsRepository(target).get_module(1, 'welcome')['enabled']
                assert TicketRepository(target).transcript(transcript['id'])['object_key'] == 'encrypted-transcripts/proof'
                restored = SuggestionRepository(target)
                assert restored.get(1234567890123456789, item['id'])['upvotes'] == 1
                assert restored.create(1, 2, 3, {'idea': 'new'})['id'] > item['id']
                assert restored.outbox_jobs.claim('after-restore') is not None
                try:
                    restore(dump, target)
                except ValueError:
                    pass
                else:
                    raise AssertionError('Populated restore target was accepted')
                corrupt = Path(directory) / 'corrupt.dump'
                corrupt.write_bytes(dump.read_bytes()[:200])
                try:
                    restore(corrupt, invalid)
                except RuntimeError:
                    pass
                else:
                    raise AssertionError('Truncated dump was accepted')
                assert inventory(invalid)['tables'] == []
            print(json.dumps({'restored_tables': len(before['tables']), 'dump_bytes': result['bytes'],
                'large_ids': 'preserved', 'identity': 'advanced', 'queue': 'claimable', 'failed_restore': 'empty', 'settings': 'preserved', 'transcript_reference': 'preserved'}))
    finally:
        for url in urls:
            close_pools(url)
        with connect(base, autocommit=True) as admin:
            for name in reversed(created):
                admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(name)))


if __name__ == '__main__':
    main()
