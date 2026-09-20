"""Admission integrated with actual Desktop transactions, without GUI input."""
import tempfile
import threading
import unittest
from unittest.mock import patch
from luda.common import DesktopError, operation_scope, subprocess_environment
from luda.desktop import Desktop


class DesktopAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.patch=patch('luda.desktop.tempfile.gettempdir',return_value=self.directory.name)
        self.patch.start();self.addCleanup(self.patch.stop)
        self.a=Desktop(environment={'DISPLAY':':test','PROBE':'a'})
        self.b=Desktop(environment={'DISPLAY':':test','PROBE':'b'})
        self.addCleanup(self.a.close);self.addCleanup(self.b.close)
    def test_waiter_gets_next_transaction_and_environment(self):
        with self.a.transaction():
            self.assertEqual(subprocess_environment()['PROBE'],'a')
            with self.assertRaises(DesktopError):
                with self.b.transaction():self.fail('concurrent entry')
        for _ in range(10):
            with self.assertRaises(DesktopError) as error:
                with self.a.transaction():self.fail('overtook waiter')
            self.assertEqual(error.exception.details['queue_position'],2)
        with self.b.transaction():self.assertEqual(subprocess_environment()['PROBE'],'b')
        with self.a.transaction():pass
    def test_cancelling_pending_transaction_removes_priority(self):
        with self.a.transaction():
            with self.assertRaises(DesktopError):
                with self.b.transaction():pass
        event=threading.Event();event.set()
        with operation_scope(cancelled=event),self.assertRaises(DesktopError):
            with self.b.transaction():self.fail()
        with self.a.transaction():pass
    def test_closed_waiter_releases_priority(self):
        with self.a.transaction():
            with self.assertRaises(DesktopError):
                with self.b.transaction():pass
        self.b.close()
        with self.a.transaction():pass
    def test_failure_after_admission_releases_both_locks(self):
        with self.assertRaisesRegex(RuntimeError,'fixture'):
            with self.a.transaction():raise RuntimeError('fixture')
        with self.b.transaction():pass
        with self.a.transaction():pass


if __name__=='__main__':unittest.main()
