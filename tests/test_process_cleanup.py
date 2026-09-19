"""Real subprocess descendants and repeated timeout resource checks."""
import os
from pathlib import Path
import signal
import sys
import tempfile
import threading
import time
import unittest

from luda.common import DesktopError, operation_scope, run


class ProcessCleanup(unittest.TestCase):
    def test_timeout_kills_descendant_before_delayed_effect(self):
        with tempfile.TemporaryDirectory() as folder:
            sentinel = Path(folder) / 'late-effect'
            # The child inherits the process group. A delayed write is an
            # independent oracle: timing out the parent alone is insufficient.
            child = 'import pathlib,time,sys;time.sleep(.35);pathlib.Path(sys.argv[1]).write_text("late")'
            parent = 'import subprocess,sys,time;subprocess.Popen([sys.executable,"-c",sys.argv[1],sys.argv[2]]);time.sleep(30)'
            with self.assertRaises(DesktopError) as raised:
                run([sys.executable, '-c', parent, child, str(sentinel)], timeout=.1, effect='uncertain')
            self.assertEqual(raised.exception.effect, 'uncertain')
            time.sleep(.4)
            self.assertFalse(sentinel.exists(), 'A descendant mutated state after timeout')

    def test_cancelled_read_after_mutation_keeps_uncertain_effect(self):
        cancel = threading.Event()
        with operation_scope(cancelled=cancel):
            run([sys.executable, '-c', 'pass'], effect='uncertain')
            cancel.set()
            with self.assertRaises(DesktopError) as raised:
                run([sys.executable, '-c', 'pass'])
            self.assertEqual(raised.exception.code, 'CANCELLED')
            self.assertEqual(raised.exception.effect, 'uncertain')

    def test_repeated_timeouts_do_not_leak_pipe_descriptors(self):
        before = len(os.listdir('/proc/self/fd'))
        for _ in range(8):
            with self.assertRaises(DesktopError):
                run([sys.executable, '-c', 'import time;time.sleep(30)'], timeout=.01)
        after = len(os.listdir('/proc/self/fd'))
        self.assertLessEqual(after, before + 1)

    def test_detached_descendant_cannot_hold_timeout_open_forever(self):
        with tempfile.TemporaryDirectory() as folder:
            pidfile = Path(folder) / 'pid'
            child = 'import time;time.sleep(30)'
            parent = 'import subprocess,sys,pathlib,time;p=subprocess.Popen([sys.executable,"-c",sys.argv[1]],start_new_session=True);pathlib.Path(sys.argv[2]).write_text(str(p.pid));time.sleep(30)'
            began = time.monotonic()
            try:
                with self.assertRaises(DesktopError):
                    run([sys.executable, '-c', parent, child, str(pidfile)], timeout=.15)
                self.assertLess(time.monotonic() - began, 2.5)
            finally:
                if pidfile.exists():
                    try:
                        os.kill(int(pidfile.read_text()), signal.SIGKILL)
                    except ProcessLookupError:
                        pass


if __name__ == '__main__':
    unittest.main()
