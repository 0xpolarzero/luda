import asyncio
from contextlib import contextmanager, nullcontext
import json
import threading
import unittest
from unittest.mock import Mock, patch

from luda import server


class QuarantineOwnership(unittest.IsolatedAsyncioTestCase):
    async def test_cancelled_rejected_request_cannot_clear_another_recovery(self):
        long_started = threading.Event()
        long_release = threading.Event()
        short_started = threading.Event()
        short_release = threading.Event()
        class Backend:
            control = Mock()
            def transaction(self):
                return nullcontext()
            def blocked(self):
                long_started.set()
                long_release.wait(3)
                return {'effect': 'dispatched'}
        real_execute = server.execute
        def delayed_dispatch(method, *args, **kwargs):
            if method == 'rejected':
                short_started.set()
                short_release.wait(3)
            return real_execute(method, *args, **kwargs)
        with patch.object(server, 'get_backend', return_value=Backend()), patch.object(server, 'execute', side_effect=delayed_dispatch):
            first = asyncio.create_task(server.execute_async('blocked'))
            second = None
            try:
                self.assertTrue(await asyncio.to_thread(long_started.wait, 1))
                first.cancel()
                await asyncio.sleep(.02)
                self.assertTrue(server._quarantined.is_set())
                second = asyncio.create_task(server.execute_async('rejected'))
                self.assertTrue(await asyncio.to_thread(short_started.wait, 1))
                second.cancel()
                await asyncio.sleep(.02)
                short_release.set()
                with self.assertRaises(asyncio.CancelledError):
                    await second
                status = json.loads((await server.desktop_status()).content[0].text)
                self.assertTrue(status['recovering'], 'short cancelled rejection cleared the still-running worker recovery')
            finally:
                short_release.set()
                long_release.set()
                for task in (first, second):
                    if task is not None:
                        try:await task
                        except asyncio.CancelledError:pass
            self.assertFalse(server._quarantined.is_set())

    async def test_timed_out_cleanup_releases_only_on_worker_completion(self):
        started = threading.Event()
        release = threading.Event()
        class Backend:
            control = Mock()
            def transaction(self):return nullcontext()
            def blocked(self):
                started.set()
                release.wait(5)
                return {'effect':'dispatched'}
        with patch.object(server, 'get_backend', return_value=Backend()):
            task = asyncio.create_task(server.execute_async('blocked'))
            try:
                self.assertTrue(await asyncio.to_thread(started.wait, 1))
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):await task
                self.assertTrue(server._quarantined.is_set())
                blocked = await server.execute_async('blocked')
                self.assertEqual(json.loads(blocked.content[0].text)['code'], 'BUSY')
            finally:
                release.set()
                for _ in range(100):
                    if not server._quarantined.is_set():break
                    await asyncio.sleep(.01)
            self.assertFalse(server._quarantined.is_set())
            self.assertEqual(server._quarantine_owners, set())


class ControlReconnectOrdering(unittest.TestCase):
    def test_pause_finishes_on_selected_backend_before_swap(self):
        control_started = threading.Event()
        finish_control = threading.Event()
        reconnect_started = threading.Event()
        reconnect_done = threading.Event()
        responses = {}
        old = Mock()
        new = Mock()
        def paused(value):
            control_started.set()
            self.assertTrue(finish_control.wait(2))
            return {'paused': value, 'revision': 1}
        old.control.set_paused.side_effect = paused
        @contextmanager
        def prepared(*args):
            yield new, {'effect': 'verified'}
        def control():
            responses['control'] = asyncio.run(server.desktop_control('pause'))
        def reconnect():
            reconnect_started.set()
            responses['reconnect'] = server.execute('reconnect')
            reconnect_done.set()
        with patch.object(server, 'backend', old), patch.object(server, 'prepare_reconnect', side_effect=prepared), patch.object(server.atexit, 'register'), patch.object(server.atexit, 'unregister'):
            first = threading.Thread(target=control)
            second = threading.Thread(target=reconnect)
            first.start()
            self.assertTrue(control_started.wait(1))
            second.start()
            try:
                self.assertTrue(reconnect_started.wait(1))
                self.assertFalse(reconnect_done.wait(.1), 'backend swapped while old display pause was unfinished')
                self.assertIs(server.backend, old)
            finally:
                finish_control.set()
                first.join(2)
                second.join(2)
            self.assertFalse(first.is_alive() or second.is_alive())
            self.assertIs(server.backend, new)
            self.assertFalse(responses['control'].isError)
            self.assertFalse(responses['reconnect'].isError)
            old.close.assert_called_once()

    def test_control_does_not_wait_for_operation_gate(self):
        desktop = Mock()
        desktop.control.status.return_value = {'paused': False, 'revision': 0}
        with patch.object(server, 'backend', desktop), server._operation_gate:
            result = asyncio.run(server.desktop_control())
        self.assertFalse(result.isError)


if __name__ == '__main__':
    unittest.main()
