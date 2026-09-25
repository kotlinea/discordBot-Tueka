"""Recovery boundaries: content/key integrity, safe archives and held writers."""
import asyncio
import io
import json
import subprocess
from pathlib import Path
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from cryptography.fernet import Fernet
from database import transaction
from database.testing import temporary_database
from deploy import compose
from deploy.recovery import backup, digest, load_bundle, validate_target, locked, release, running
from recovery.storage import export_blobs, import_blobs, key_generations, verify
from ticketing import TicketRepository
from ticketing.transcripts import TranscriptStorage


def settings(url, root, key):
    return SimpleNamespace(database_url=url, data_dir=Path(root), ticket_encryption_key=key,
        social_token_encryption_key=None, **{'ticket_s3_' + name: None for name in
        ('endpoint_url', 'region', 'bucket', 'access_key_id', 'secret_access_key', 'prefix')})


class RecoveryStorageTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        context = temporary_database()
        self.url = context.__enter__()
        self.addCleanup(context.__exit__, None, None, None)
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.key = Fernet.generate_key().decode()
        self.settings = settings(self.url, self.root / 'source', self.key)
        self.store = TranscriptStorage(self.settings.data_dir / 'ticket-transcripts', self.key)
        self.repo = TicketRepository(self.url)
        team = self.repo.save_team(1, {'name': 'Staff', 'role_ids': [50]})
        panel = self.repo.save_panel(1, {'name': 'Recovery', 'mode': 'channel', 'category_id': 10, 'team_id': team['id']})
        self.ticket = self.repo.reserve_ticket(1, panel['id'], 2, 'recover-test', {'answer': self.store.encrypt_text('private answer')})
        self.blob = await self.store.save(1, self.ticket['id'], {'body': 'private transcript'})
        self.repo.save_transcript(self.ticket['id'], self.blob.backend, self.blob.object_key, self.blob.content_hash, self.blob.byte_size, 9999999999)

    async def test_roundtrip_verifies_all_encrypted_content_and_localizes_s3(self):
        attachment = await self.store.save_attachment(1, self.ticket['id'], 123, b'private attachment')
        self.repo.save_attachment(self.ticket['id'], 123, 'test.txt', 'text/plain', attachment.byte_size, attachment.backend, attachment.object_key, attachment.content_hash)
        with transaction(self.url) as c:
            c.execute("UPDATE ticket_transcripts SET backend='s3'")
        archive = io.BytesIO()
        with patch.object(TranscriptStorage, '_download_s3', return_value=self.store._local_path(self.blob.object_key).read_bytes()):
            export_blobs(self.settings, archive)
        self.assertNotIn(b'private transcript', archive.getvalue())
        self.assertNotIn(b'private attachment', archive.getvalue())
        target = settings(self.url, self.root / 'restored', self.key)
        import_blobs(target.data_dir / 'ticket-transcripts', io.BytesIO(archive.getvalue()))
        result = await verify(target, localize=True)
        self.assertEqual(result['verified_blobs'], 2)
        self.assertEqual(result['verified_encrypted_values'], 1)
        self.assertEqual(self.repo.transcript_for_ticket(self.ticket['id'])['backend'], 'local')
        with self.assertRaises(ValueError):
            import_blobs(target.data_dir / 'ticket-transcripts', io.BytesIO(archive.getvalue()))

    async def test_wrong_key_and_corrupt_blob_refuse_verification(self):
        wrong = settings(self.url, self.settings.data_dir, Fernet.generate_key().decode())
        with self.assertRaises(ValueError):
            await verify(wrong)
        self.store._local_path(self.blob.object_key).write_bytes(b'corrupt')
        with self.assertRaises(ValueError):
            await verify(self.settings)

    async def test_missing_remote_object_is_not_silently_backed_up_from_local_fallback(self):
        with transaction(self.url) as c:
            c.execute("UPDATE ticket_transcripts SET backend='s3'")
        with patch.object(TranscriptStorage, '_download_s3', side_effect=OSError('offline')):
            with self.assertRaises(OSError):
                export_blobs(self.settings, io.BytesIO())

    async def test_corrupt_export_and_database_ciphertext_fail_closed(self):
        with transaction(self.url) as c:
            c.execute("UPDATE tickets_v2 SET form_answers_json='{" + '"answer":"corrupt"' + "}'")
        with self.assertRaises(ValueError):
            await verify(self.settings)
        self.store._local_path(self.blob.object_key).write_bytes(b'corrupt')
        with self.assertRaises(Exception):
            export_blobs(self.settings, io.BytesIO())


class RecoveryBoundaryTests(unittest.TestCase):
    def test_writer_detection_uses_container_state_after_recreation(self):
        listings = ['old-bot\nnew-bot\n', 'dashboard\n', '']
        stopped = json.dumps({'Running': False, 'Restarting': False})
        with patch('deploy.recovery.compose.execute', side_effect=[SimpleNamespace(stdout=s) for s in listings]), patch(
            'deploy.recovery.subprocess.check_output', side_effect=[stopped + '\n' + stopped, stopped]
        ):
            self.assertEqual(running('source'), set())

    def test_writer_detection_includes_running_and_restarting_replicas(self):
        stopped = json.dumps({'Running': False, 'Restarting': False})
        for state in ({'Running': True, 'Restarting': False}, {'Running': False, 'Restarting': True}):
            with self.subTest(state=state), patch('deploy.recovery.compose.execute', side_effect=[
                SimpleNamespace(stdout='old\nnew\n'), SimpleNamespace(stdout=''), SimpleNamespace(stdout='')
            ]), patch('deploy.recovery.subprocess.check_output', return_value=stopped + '\n' + json.dumps(state)):
                self.assertEqual(running('source'), {'bot'})

    def test_writer_detection_fails_closed_when_inspection_fails_or_is_incomplete(self):
        with patch('deploy.recovery.compose.execute', return_value=SimpleNamespace(stdout='container\n')):
            with patch('deploy.recovery.subprocess.check_output', side_effect=subprocess.CalledProcessError(1, 'docker')):
                with self.assertRaises(subprocess.CalledProcessError):
                    running('source')
            with patch('deploy.recovery.subprocess.check_output', return_value=''):
                with self.assertRaisesRegex(RuntimeError, 'every application'):
                    running('source')

    def test_mutable_dev_source_cannot_be_claimed_as_an_image_matched_snapshot(self):
        with tempfile.TemporaryDirectory() as directory, patch('deploy.recovery.read', return_value=({'environment': 'dev'}, {})), patch('deploy.recovery.image_id') as image:
            with self.assertRaisesRegex(ValueError, 'mutable source'):
                backup(directory, Path(directory) / 'snapshot')
            image.assert_not_called()

    def test_archive_refuses_traversal_links_and_duplicate_files(self):
        for names, kind in [(['../escape'], tarfile.REGTYPE), (['/absolute'], tarfile.REGTYPE),
                            (['link'], tarfile.SYMTYPE), (['same', 'same'], tarfile.REGTYPE)]:
            with self.subTest(names=names), tempfile.TemporaryDirectory() as directory:
                data = io.BytesIO()
                with tarfile.open(fileobj=data, mode='w') as archive:
                    for name in names:
                        item = tarfile.TarInfo(name)
                        item.type, item.size, item.linkname = kind, 1 if kind == tarfile.REGTYPE else 0, '../outside'
                        archive.addfile(item, io.BytesIO(b'x') if item.size else None)
                with self.assertRaises(ValueError):
                    import_blobs(Path(directory) / 'target', io.BytesIO(data.getvalue()))
                self.assertFalse((Path(directory) / 'escape').exists())

    def test_bundle_checksums_and_key_environment_image_identity_are_mandatory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('database.dump', 'transcripts.tar'):
                (root / name).write_bytes(b'artifact')
            manifest = {'format': 1, 'artifacts': {name: digest(root / name) for name in ('database.dump', 'transcripts.tar')}}
            (root / 'manifest.json').write_text(json.dumps(manifest))
            self.assertEqual(load_bundle(root), manifest)
            (root / 'database.dump').write_bytes(b'changed')
            with self.assertRaises(ValueError):
                load_bundle(root)
        secrets = {'DISCORD_CLIENT_ID': '1', 'TICKET_ENCRYPTION_KEY': 'key'}
        manifest.update(environment='stage', source_project='tueka-stage-source', image_id='image', discord_client_id='1', key_generations=key_generations(secrets))
        target = {'environment': 'stage', 'project': 'tueka-stage-restored', 'image': 'image'}
        with patch('deploy.recovery.image_id', return_value='image'):
            validate_target(target, secrets, manifest)
            for change in ({'environment': 'prod'}, {'project': 'tueka-stage-source'}):
                with self.assertRaises(ValueError):
                    validate_target({**target, **change}, secrets, manifest)
            with self.assertRaises(ValueError):
                validate_target(target, {**secrets, 'TICKET_ENCRYPTION_KEY': 'wrong'}, manifest)
        with patch('deploy.recovery.image_id', return_value='other'), self.assertRaises(ValueError):
            validate_target(target, secrets, manifest)

    def test_recovery_hold_and_lock_block_normal_startup(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with locked(root):
                with self.assertRaisesRegex(ValueError, 'Operation lock already exists'):
                    with locked(root):
                        pass
                self.assertTrue((root / '.recovery.lock').exists())
                with self.assertRaisesRegex(ValueError, 'Recovery'):
                    compose.up(root)
            self.assertFalse((root / '.recovery.lock').exists())
            for name in ('recovery-pending.json', 'recovery-fence.json'):
                (root / name).write_text('{}')
                with self.assertRaisesRegex(ValueError, 'Recovery'):
                    compose.up(root)
                (root / name).unlink()
            with self.assertRaisesRegex(ValueError, 'reconciled'):
                release(root)
