import asyncio
from contextlib import nullcontext
import json
import sys
import threading
import unittest
from unittest.mock import patch, Mock

from luda.common import DesktopError, mark_effect, run
from luda import server


class FakeDesktop:
    def __init__(self):
        self.started = threading.Event()
        self.control = Mock()
    def transaction(self): return nullcontext()
    def blocked(self):
        self.started.set()
        run([sys.executable, '-c', 'import time;time.sleep(20)'], effect='uncertain')
    def after_effect_failure(self):
        mark_effect()
        raise DesktopError('FOCUS_CHANGED','changed after input')
    def ready(self): return {'ready':True}


class MCPCancellation(unittest.IsolatedAsyncioTestCase):
    async def test_cancelled_worker_stops_and_server_recovers(self):
        desktop = FakeDesktop()
        with patch.object(server,'get_backend',return_value=desktop):
            task = asyncio.create_task(server.execute_async('blocked'))
            await asyncio.to_thread(desktop.started.wait, 1)
            await asyncio.sleep(.05)
            task.cancel()
            with self.assertRaises(asyncio.CancelledError): await task
            result = await server.execute_async('ready')
        self.assertFalse(result.isError)
        self.assertFalse(server._quarantined.is_set())
        status = await server.desktop_status()
        events = json.loads(status.content[0].text)['operations']
        blocked = [e for e in events if e['method']=='blocked'][-1]
        self.assertEqual(blocked['code'],'CANCELLED')
        self.assertEqual(blocked['effect'],'uncertain')
        self.assertNotIn('text',blocked)

    async def test_later_failure_preserves_prior_effect(self):
        with patch.object(server,'get_backend',return_value=FakeDesktop()):
            result = await server.execute_async('after_effect_failure')
        payload = json.loads(result.content[0].text)
        self.assertTrue(result.isError)
        self.assertEqual(payload['effect'],'uncertain')
        self.assertTrue(payload['details']['prior_effects_possible'])
