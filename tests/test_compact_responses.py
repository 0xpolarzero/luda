"""Public tool text stays lossless and private when JSON whitespace is reduced."""
from collections import deque
from contextlib import nullcontext
from copy import deepcopy
import json
import unittest
from unittest.mock import Mock, patch

from luda import server
from luda.common import DesktopError


class CompactResponses(unittest.IsolatedAsyncioTestCase):
    async def test_public_responses_preserve_nested_unicode_and_error_privacy(self):
        fixture = {'elements': [
            {'element_id': 'e1', 'name': '日本語 café 👩🏽‍💻', 'parent_id': None,
             'states': ['enabled', 'showing'], 'bounds': {'x': 1, 'y': 2},
             'text': 'two words\n\ttail', 'protected': False},
            {'element_id': 'e2', 'name': '', 'parent_id': 'e1', 'actions': []},
        ], 'truncated': False}
        backend = Mock()
        backend.transaction.side_effect = nullcontext
        backend.inspect.return_value = deepcopy(fixture)
        backend.control.status.return_value = {'paused': False, 'display': ':99'}
        secret = 'synthetic-private-exception-内容'

        def check(result, expected, *, ascii=False, error=False):
            self.assertEqual(result.isError, error)
            text = result.content[0].text
            self.assertEqual(json.loads(text), expected)
            self.assertEqual(text, json.dumps(expected, ensure_ascii=ascii,
                                              separators=(',', ':')))
            self.assertLess(len(text.encode()), len(json.dumps(
                expected, ensure_ascii=ascii).encode()))
            self.assertNotIn(secret, text)

        with patch.object(server, 'get_backend', return_value=backend), \
                patch.object(server, '_history', deque(maxlen=32)):
            result = await server.mcp.call_tool('desktop_inspect', {'window_id': 'w'})
            payload = json.loads(result.content[0].text)
            metadata = {key: payload[key] for key in ('operation_id', 'elapsed_ms')}
            self.assertRegex(metadata['operation_id'], r'^[0-9a-f]{32}$')
            self.assertIsInstance(metadata['elapsed_ms'], int)
            check(result, {'ok': True, **metadata, **fixture})
            self.assertIn('日本語', result.content[0].text)

            backend.inspect.side_effect = DesktopError(
                'STALE_TARGET', 'Inspect again: expired 日本語.',
                details={'reason': 'expired', 'nested': {'values': [None, 'a b']}})
            result = await server.mcp.call_tool('desktop_inspect', {'window_id': 'w'})
            payload = json.loads(result.content[0].text)
            check(result, {'ok': False, 'code': 'STALE_TARGET',
                           'message': 'Inspect again: expired 日本語.', 'effect': 'none',
                           'details': {'reason': 'expired', 'nested': {'values': [None, 'a b']}},
                           'operation_id': payload['operation_id'],
                           'elapsed_ms': payload['elapsed_ms']}, error=True)

            backend.inspect.side_effect = RuntimeError(secret)
            result = await server.mcp.call_tool('desktop_inspect', {'window_id': 'w'})
            payload = json.loads(result.content[0].text)
            check(result, {'ok': False, 'code': 'INTERNAL_ERROR',
                           'message': 'Unexpected backend failure. Inspect desktop_status and current application state before retrying; input may already have occurred.', 'effect': 'uncertain',
                           'operation_id': payload['operation_id'],
                           'elapsed_ms': payload['elapsed_ms']}, error=True)
            check(await server.mcp.call_tool('desktop_control', {}),
                  {'ok': True, 'paused': False, 'display': ':99'}, ascii=True)
            check(await server.mcp.call_tool('desktop_status', {}),
                  {'ok': True, 'recovering': False,
                   'operations': list(server._history)}, ascii=True)
            self.assertEqual(len(server._history), 3)
            self.assertNotIn(secret, repr(server._history))


if __name__ == '__main__':
    unittest.main()
