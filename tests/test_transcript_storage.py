"""Dashboard readers must not write to the shared transcript volume on startup."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cryptography.fernet import Fernet
from ticketing.transcripts import TranscriptStorage


class TranscriptReaderTests(unittest.IsolatedAsyncioTestCase):
    async def test_reader_initialization_and_decryption_need_no_directory_writes(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / 'transcripts'
            key = Fernet.generate_key().decode()
            writer = TranscriptStorage(root, key)
            self.assertFalse(root.exists())
            stored = await writer.save(1, 2, {'message': 'retained'})
            with patch.object(Path, 'mkdir', side_effect=PermissionError('read-only volume')):
                reader = TranscriptStorage(root, key)
                self.assertEqual(await reader.load(stored.backend, stored.object_key, stored.content_hash), {'message': 'retained'})
