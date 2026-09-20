"""Keyboard guardian ownership must quarantine every MCP mutation, not just keys."""
import json
import subprocess
import sys
import time
import unittest
from unittest.mock import patch

from luda import keyboard, server


class KeyboardServerRecovery(unittest.TestCase):
    def test_server_registers_keyboard_ownership_hooks(self):
        self.assertIs(keyboard._retain_recovery, server._retain_quarantine)
        self.assertIs(keyboard._release_recovery, server._release_quarantine)

    def test_pending_guardian_gates_all_operations_and_preserves_other_owner(self):
        child = subprocess.Popen([sys.executable, '-c', 'import sys,json;sys.stdin.readline();print(json.dumps({"done":True,"armed":True}))'], stdin=subprocess.PIPE, stdout=subprocess.PIPE)
        previous = set(keyboard._pending_recoveries)
        other = object()
        try:
            keyboard._retain_guardian(child, b'')
            self.assertTrue(server._quarantined.is_set())
            with patch.object(server, 'get_backend') as backend:
                response = server.execute('pointer', 'owned-fixture')
                self.assertEqual(json.loads(response.content[0].text)['code'], 'BUSY')
                backend.assert_not_called()
            server._retain_quarantine(other)
            child.stdin.write(b'finish\n')
            child.stdin.close()
            child.wait(timeout=2)
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                with keyboard._recovery_lock:
                    pending = set(keyboard._pending_recoveries) - previous
                if not pending:break
                time.sleep(.01)
            self.assertFalse(pending)
            self.assertTrue(server._quarantined.is_set(), 'guardian completion cleared unrelated operation recovery')
            server._release_quarantine(other)
            self.assertFalse(server._quarantined.is_set())
        finally:
            server._release_quarantine(other)
            if child.poll() is None:
                child.kill()
                child.wait(timeout=2)
            if not child.stdin.closed:child.stdin.close()
            if not child.stdout.closed:child.stdout.close()
            with keyboard._recovery_lock:
                for token in set(keyboard._pending_recoveries) - previous:
                    keyboard._pending_recoveries.pop(token, None)
                    server._release_quarantine(token)


if __name__ == '__main__':
    unittest.main()
