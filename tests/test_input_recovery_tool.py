import json
import unittest
from unittest.mock import Mock, patch

from luda import server
from luda.common import subprocess_environment


class RecoveryTool(unittest.IsolatedAsyncioTestCase):
    async def test_recovery_works_paused_without_clearing_unrelated_quarantine(self):
        backend = Mock(environment={'DISPLAY': ':91'})
        token = object()
        server._retain_quarantine(token)
        def recover():
            self.assertEqual(subprocess_environment()['DISPLAY'], ':91')
            return {'effect': 'none', 'pending_count': 1, 'resolved_count': 0}
        try:
            with patch.object(server, 'get_backend', return_value=backend), patch.object(server, 'recover_keyboard_input', side_effect=recover):
                result = json.loads((await server.desktop_recover_input()).content[0].text)
                self.assertTrue(result['ok'])
                self.assertTrue(result['recovering'])
                self.assertEqual(result['pending_count'], 1)
                backend.transaction.assert_not_called()
                backend.control.require_active.assert_not_called()
                blocked = json.loads(server.execute('observe').content[0].text)
                self.assertEqual(blocked['code'], 'BUSY')
        finally:
            server._release_quarantine(token)

    async def test_recovery_does_not_race_running_operation(self):
        server._operation_gate.acquire()
        try:
            with patch.object(server, 'recover_keyboard_input') as recover:
                result = json.loads((await server.desktop_recover_input()).content[0].text)
                self.assertEqual(result['code'], 'BUSY')
                recover.assert_not_called()
        finally:
            server._operation_gate.release()

    async def test_completed_recovery_reports_released_ownership(self):
        token = object()
        server._retain_quarantine(token)
        def recover():
            server._release_quarantine(token)
            return {'effect': 'uncertain', 'pending_count': 0, 'resolved_count': 1}
        try:
            with patch.object(server, 'get_backend', return_value=Mock(environment={})), patch.object(server, 'recover_keyboard_input', side_effect=recover):
                result = json.loads((await server.desktop_recover_input()).content[0].text)
                self.assertFalse(result['recovering'])
                self.assertEqual(result['effect'], 'uncertain')
                self.assertEqual(result['resolved_count'], 1)
        finally:
            server._release_quarantine(token)
