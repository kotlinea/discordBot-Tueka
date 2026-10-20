"""Offline X stream author identity boundaries for stale rules."""
import asyncio
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock

import httpx

from social.worker import SocialWorker


class OnePost(httpx.AsyncByteStream):
    def __init__(self, body):
        self.body = body

    async def __aiter__(self):
        yield (json.dumps(self.body, ensure_ascii=False) + '\n').encode('utf-8')
        raise asyncio.CancelledError


class XStreamReviewTests(unittest.IsolatedAsyncioTestCase):
    async def _stream(self, target, post):
        worker = object.__new__(SocialWorker)
        worker.settings = SimpleNamespace(social_x_mode='stream', x_bearer_token='fixture')
        enqueue = Mock()
        worker.repository = SimpleNamespace(social_target=Mock(return_value=target), enqueue_social_event_v2=enqueue)
        worker._replace_x_rules = AsyncMock()
        body = {'data': post, 'matching_rules': [{'tag': 'tueka:1'}]}
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda request: httpx.Response(200, stream=OnePost(body)))) as client:
            with self.assertRaises(asyncio.CancelledError):
                await worker.x_stream_loop(client)
        return enqueue

    async def test_stale_handle_rule_cannot_attribute_new_owner_to_original_account(self):
        enqueue = await self._stream({'provider': 'x', 'external_id': '42', 'account_key': 'creator', 'handle': 'creator'},
                                     {'id': '20', 'author_id': '99', 'text': '別人'})
        enqueue.assert_not_called()

    async def test_unresolved_target_or_missing_author_cannot_accept_stream_event(self):
        for target_id, author_id in [(None, '42'), ('42', None)]:
            with self.subTest(target_id=target_id, author_id=author_id):
                enqueue = await self._stream({'provider': 'x', 'external_id': target_id, 'account_key': 'creator', 'handle': 'creator'},
                                             {'id': '20', 'author_id': author_id, 'text': '本文'})
                enqueue.assert_not_called()

    async def test_matching_author_is_enqueued_with_canonical_account_id(self):
        enqueue = await self._stream({'provider': 'x', 'external_id': '42', 'account_key': 'creator', 'handle': 'creator'},
                                     {'id': '20', 'author_id': '42', 'text': '日本語🌸'})
        enqueue.assert_called_once()
        args = enqueue.call_args.args
        self.assertEqual(args[:4], ('x', '20', '42', 'post'))
        self.assertEqual(args[4]['text'], '日本語🌸')


if __name__ == '__main__':
    unittest.main()
