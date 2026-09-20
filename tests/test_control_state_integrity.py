import errno
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from luda.common import DesktopError
from luda.control import Control


class ControlIntegrity(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.control = Control(Path(self.directory.name), 'display')

    def state(self, content):
        self.control.path.write_bytes(content)
        self.control.path.chmod(0o600)

    def test_fifo_fails_closed_without_waiting_for_writer(self):
        os.mkfifo(self.control.path, 0o600)
        code = '''from pathlib import Path
import sys
from luda.control import Control
from luda.common import DesktopError
try:Control(Path(sys.argv[1]),'display').status()
except DesktopError as exc:assert exc.code=='CONTROL_UNAVAILABLE'
else:raise AssertionError('unsafe control accepted')
'''
        result = subprocess.run([sys.executable, '-c', code, self.directory.name], capture_output=True, text=True, timeout=1)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_oversized_state_rejected_without_unbounded_parse(self):
        self.state(b' ' * 100000 + b'{"paused": false, "revision": 0}')
        with self.assertRaises(DesktopError) as caught:
            self.control.status()
        self.assertEqual(caught.exception.code, 'CONTROL_UNAVAILABLE')

    def test_boolean_negative_and_extra_state_fail_closed(self):
        for data in ({'paused':False,'revision':True}, {'paused':False,'revision':-1}, {'paused':False,'revision':0,'private':'unexpected'}, {'paused':False,'revision':0,'updated_at':10**2000}):
            with self.subTest(data=data):
                self.state(json.dumps(data).encode())
                with self.assertRaises(DesktopError) as caught:
                    self.control.require_active()
                self.assertEqual(caught.exception.code, 'CONTROL_UNAVAILABLE')

    def test_linked_or_public_state_and_lock_refused(self):
        self.state(b'{"paused": false, "revision": 0}')
        self.control.path.chmod(0o644)
        with self.assertRaises(DesktopError):self.control.status()
        self.control.path.chmod(0o600)
        alias = Path(self.directory.name) / 'alias'
        os.link(self.control.path, alias)
        with self.assertRaises(DesktopError):self.control.status()
        alias.unlink()
        os.mkfifo(self.control.lock_path, 0o600)
        with self.assertRaises(DesktopError):self.control.set_paused(True)
        self.assertFalse(self.control.status()['paused'])

    def test_write_failure_preserves_pause_and_closes_lock(self):
        self.control.set_paused(True)
        before = len(list(Path('/proc/self/fd').iterdir()))
        with patch('luda.control.os.fsync', side_effect=OSError(errno.ENOSPC, '/private/state')):
            with self.assertRaises(DesktopError) as caught:
                self.control.set_paused(False)
        self.assertEqual(caught.exception.code, 'CONTROL_UNAVAILABLE')
        self.assertNotIn('/private', str(caught.exception))
        self.assertTrue(self.control.status()['paused'])
        self.assertEqual(len(list(Path('/proc/self/fd').iterdir())), before)
        self.assertEqual({p.name for p in Path(self.directory.name).iterdir()}, {self.control.path.name, self.control.lock_path.name})
        self.control.set_paused(False)
        self.assertFalse(self.control.status()['paused'])


if __name__ == '__main__':
    unittest.main()
