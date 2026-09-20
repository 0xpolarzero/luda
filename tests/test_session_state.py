import unittest
from unittest.mock import patch
from luda.session_state import summarize,session_state
from luda.common import DesktopError

class SessionStateTests(unittest.TestCase):
    def test_unavailable_never_means_unlocked(self):
        self.assertEqual(summarize([])['state'],'unknown')
        self.assertIsNone(summarize([])['input_ready'])
    def test_active_saver_is_not_mislabeled_locked(self):
        result=summarize([{'kind':'screensaver','active':True}])
        self.assertEqual(result['state'],'screensaver_active');self.assertFalse(result['input_ready'])
    def test_reported_lock_takes_precedence(self):
        self.assertEqual(summarize([{'kind':'lock_hint','active':True},{'kind':'screensaver','active':False}])['state'],'locked')
    def test_inactive_hint_does_not_prove_input_ready(self):
        self.assertIsNone(summarize([{'kind':'lock_hint','active':False}])['input_ready'])
    def test_provider_failure_contains_no_sensitive_error_text(self):
        with patch('luda.session_state.run',side_effect=DesktopError('BACKEND_ERROR','private-bus-address')):
            result=session_state()
        self.assertNotIn('private-bus-address',str(result));self.assertEqual(result['state'],'unknown')
    def test_cancellation_propagates(self):
        with patch('luda.session_state.run',side_effect=DesktopError('CANCELLED','test')),self.assertRaises(DesktopError):session_state()

if __name__=='__main__':unittest.main()
