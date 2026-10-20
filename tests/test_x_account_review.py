"""Offline numeric X account ID resolution boundaries."""
from types import SimpleNamespace
import unittest

import httpx

from social.providers.x import XAdapter


class XAccountReviewTests(unittest.IsolatedAsyncioTestCase):
    async def test_numeric_account_id_resolves_by_id_and_uses_resolved_handle(self):
        paths = []
        def respond(request):
            paths.append(request.url.path)
            if request.url.path == '/2/users/42':
                return httpx.Response(200, json={'data': {'id': '42', 'username': 'creator', 'name': '作者🌸'}})
            if request.url.path == '/2/users/42/tweets':
                return httpx.Response(200, json={'data': [{'id': '20', 'text': '日本語🌸'}]})
            return httpx.Response(404)
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            result = await XAdapter(SimpleNamespace(x_bearer_token='fixture'), client).poll({'account_key': '42'}, initialize=True)
        self.assertEqual(paths, ['/2/users/42', '/2/users/42/tweets'])
        self.assertEqual((result.external_id, result.handle, result.display_name), ('42', 'creator', '作者🌸'))
        self.assertEqual(result.cursor, {'since_id': '20'})
        self.assertEqual(result.events, [])

    async def test_handle_still_resolves_by_username(self):
        paths = []
        def respond(request):
            paths.append(request.url.path)
            if request.url.path == '/2/users/by/username/creator':
                return httpx.Response(200, json={'data': {'id': '42', 'username': 'creator'}})
            return httpx.Response(200, json={'data': []})
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            result = await XAdapter(SimpleNamespace(x_bearer_token='fixture'), client).poll({'account_key': 'creator'}, initialize=True)
        self.assertEqual(paths, ['/2/users/by/username/creator', '/2/users/42/tweets'])
        self.assertEqual(result.external_id, '42')


if __name__ == '__main__':
    unittest.main()
