from pathlib import Path
import tempfile
import threading
import time
import unittest
import sys

from luda.common import DesktopError, operation_scope, run
from luda.control import Control


class PauseControl(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.control = Control(Path(self.directory.name),'test-display')

    def test_pause_shared_and_resume_persist(self):
        other = Control(Path(self.directory.name),'test-display')
        self.assertFalse(other.status()['paused'])
        self.control.set_paused(True)
        with self.assertRaises(DesktopError) as error: other.require_active()
        self.assertEqual(error.exception.code,'CONTROL_PAUSED')
        other.set_paused(False)
        self.control.require_active()
        self.assertEqual(self.control.status()['revision'],2)

    def test_corrupt_control_fails_closed(self):
        self.control.path.write_text('invalid JSON')
        with self.assertRaises(DesktopError) as error:self.control.require_active()
        self.assertEqual(error.exception.code,'CONTROL_UNAVAILABLE')

    def test_symlink_control_rejected(self):
        secret=Path(self.directory.name)/'unrelated';secret.write_text('private')
        self.control.path.symlink_to(secret)
        with self.assertRaises(DesktopError):self.control.status()
        self.assertEqual(secret.read_text(),'private')

    def test_pause_interrupts_running_operation_with_cleanup_available(self):
        timer=threading.Timer(.12,lambda:self.control.set_paused(True));timer.start()
        try:
            with operation_scope(guard=self.control.require_active):
                with self.assertRaises(DesktopError) as error:
                    run([sys.executable,'-c','import time;time.sleep(10)'],effect='uncertain')
                self.assertEqual(error.exception.code,'CONTROL_PAUSED')
                self.assertEqual(error.exception.effect,'uncertain')
                self.assertEqual(run([sys.executable,'-c','print("released")'],cleanup=True),b'released\n')
        finally:timer.cancel()
