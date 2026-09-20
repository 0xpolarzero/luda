"""Native CI must bound hangs and kill surviving fixture descendants."""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import time
import unittest

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('native_app_tests', SCRIPTS / 'native_app_tests.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class NativeRunnerTests(unittest.TestCase):
    def test_nonzero_suite_fails(self):
        with tempfile.TemporaryFile() as log:
            result = runner.bounded([sys.executable, '-c', 'raise SystemExit(7)'], dict(os.environ), log, 2)
        self.assertEqual(result, {'status': 'failed', 'returncode': 7})

    def test_timeout_kills_descendant_before_late_effect(self):
        self.check_descendant('import time; time.sleep(30)', .1, 'timeout')

    def test_exited_launcher_does_not_leave_fixture_alive(self):
        self.check_descendant('', 2, 'passed')

    def check_descendant(self, parent_tail, timeout, status):
        with tempfile.TemporaryDirectory() as directory:
            effect = Path(directory) / 'late-effect'
            code = "import time; from pathlib import Path; time.sleep(.5); Path(%r).write_text('orphan')" % str(effect)
            parent = 'import subprocess,sys; subprocess.Popen([sys.executable,"-c",%r]); %s' % (code, parent_tail)
            began = time.monotonic()
            with tempfile.TemporaryFile() as log:
                result = runner.bounded([sys.executable, '-c', parent], dict(os.environ), log, timeout)
            self.assertEqual(result['status'], status)
            self.assertLess(time.monotonic() - began, 2)
            time.sleep(.6)
            self.assertFalse(effect.exists(), 'owned descendant survived cleanup and mutated the filesystem')


if __name__ == '__main__':
    unittest.main()
