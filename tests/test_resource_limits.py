"""Actual kernel RLIMIT failures in isolated disposable children, not mocks."""
import json
from pathlib import Path
import subprocess
import sys
import unittest

FIXTURE=Path(__file__).with_name('rlimit_fixture.py')

@unittest.skipUnless(sys.platform.startswith('linux'),'Linux /proc and RLIMIT qualification')
class ResourceLimits(unittest.TestCase):
    def check(self,mode,effect):
        result=subprocess.run([sys.executable,str(FIXTURE),mode],capture_output=True,text=True,timeout=8)
        self.assertEqual(result.returncode,0,result.stderr)
        value=json.loads(result.stdout)
        self.assertEqual(value['error'],{'type':'DesktopError','code':'RESOURCE_UNAVAILABLE','effect':effect},value)
        self.assertLess(value['elapsed_seconds'],3)
        self.assertFalse(value['late_effect'])
        self.assertEqual(value['remaining_children'],[])
        self.assertEqual(value['fd_delta'],0)
        self.assertTrue(value['limit_restored'])
        self.assertEqual(value['recovery'],'recovered')
    def test_descriptor_exhaustion_before_backend_startup(self):self.check('startup-fd','none')
    def test_descriptor_exhaustion_before_subprocess_spawn(self):self.check('spawn-fd','none')
    def test_descriptor_exhaustion_staging_subprocess_input(self):self.check('stdin-fd','none')
    def test_address_space_exhaustion_during_readonly_capture(self):self.check('memory-capture','none')
    def test_address_space_exhaustion_after_dispatch_preserves_uncertainty(self):self.check('memory-after-dispatch','uncertain')


class ResourceFailureOrdering(unittest.TestCase):
    def test_resource_fault_after_spawn_preserves_cancellation_priority(self):
        import errno
        import threading
        from unittest.mock import patch
        from luda.common import DesktopError,operation_scope,run
        cancelled=threading.Event()
        def fault():
            cancelled.set()
            raise OSError(errno.EMFILE,'must not expose provider detail')
        with operation_scope(cancelled=cancelled),patch('luda.common.selectors.DefaultSelector',side_effect=fault):
            with self.assertRaises(DesktopError) as caught:
                run([sys.executable,'-c','import time;time.sleep(5)'],effect='uncertain')
        self.assertEqual(caught.exception.code,'CANCELLED')
        self.assertEqual(caught.exception.effect,'uncertain')

    def test_failed_spawn_retains_prior_operation_uncertainty(self):
        import errno
        from unittest.mock import patch
        from luda.common import DesktopError,operation_scope,mark_effect,run
        with operation_scope(),patch('luda.common.subprocess.Popen',side_effect=OSError(errno.ENOMEM,'private payload')):
            mark_effect()
            with self.assertRaises(DesktopError) as caught:run(['/bin/true'])
        self.assertEqual(caught.exception.code,'RESOURCE_UNAVAILABLE')
        self.assertEqual(caught.exception.effect,'uncertain')
        self.assertNotIn('private',str(caught.exception))

    def test_unknown_os_failure_not_misclassified_as_resource_exhaustion(self):
        import errno
        from unittest.mock import patch
        from luda.common import run
        with patch('luda.common.subprocess.Popen',side_effect=OSError(errno.EIO,'io failure')):
            with self.assertRaises(OSError) as caught:run(['/bin/true'])
        self.assertEqual(caught.exception.errno,errno.EIO)

if __name__=='__main__':unittest.main()
