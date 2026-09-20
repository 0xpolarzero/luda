import unittest
from unittest.mock import Mock,patch
from luda.common import DesktopError
from luda.desktop import Desktop

class WindowEnumerationTests(unittest.TestCase):
    def driver(self):
        d=Desktop.__new__(Desktop);d.windows={};d.active=Mock(return_value=None)
        return d
    def test_disappearing_dialog_retries_read_only_enumeration(self):
        d=self.driver()
        with patch('luda.desktop.run',side_effect=[DesktopError('BACKEND_ERROR','BadWindow X_GetProperty'),b'']) as run:
            self.assertEqual(d.list_windows(),[])
        self.assertEqual(run.call_count,2)
        self.assertTrue(all(c.args[0]==['wmctrl','-lp'] for c in run.call_args_list))
    def test_repeated_race_stops_after_three_attempts(self):
        with patch('luda.desktop.run',side_effect=DesktopError('BACKEND_ERROR','BadWindow X_GetProperty')) as run,self.assertRaises(DesktopError):self.driver().list_windows()
        self.assertEqual(run.call_count,3)
    def test_other_failures_and_cancellation_not_retried(self):
        for error in [DesktopError('BACKEND_ERROR','cannot connect'),DesktopError('CANCELLED','BadWindow X_GetProperty')]:
            with patch('luda.desktop.run',side_effect=error) as run,self.assertRaises(DesktopError):self.driver().list_windows()
            self.assertEqual(run.call_count,1)

if __name__=='__main__':unittest.main()
