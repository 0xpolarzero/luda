import unittest
from unittest.mock import Mock
from luda.common import DesktopError, display_identity
from luda.desktop import Desktop


class Waits(unittest.TestCase):
    def test_window_wait_observes_transition_without_input(self):
        desktop = object.__new__(Desktop)
        desktop.list_windows = Mock(side_effect=[[], [{'window_id':'w','active':True}]])
        self.assertTrue(desktop.wait_for('window_active',window_id='w',timeout=.5)['matched'])
        self.assertEqual(desktop.list_windows.call_count,2)

    def test_text_wait_requires_complete_readback(self):
        desktop = object.__new__(Desktop)
        desktop.element = Mock(return_value={'text':'prefix', 'truncated':True})
        with self.assertRaises(DesktopError) as error:
            desktop.wait_for('text_contains',element_id='e',text='prefix',timeout=0)
        self.assertEqual(error.exception.code,'VERIFICATION_LIMIT')

    def test_timeout_is_unsatisfied_condition_not_input_failure(self):
        desktop = object.__new__(Desktop)
        desktop.list_windows = Mock(return_value=[])
        result = desktop.wait_for('window_present',window_id='w',timeout=0)
        self.assertFalse(result['matched'])
        self.assertEqual(result['effect'],'none')
        self.assertEqual(desktop.list_windows.call_count,1)

    def test_invalid_wait_rejected_before_observation(self):
        desktop = object.__new__(Desktop)
        desktop.list_windows = Mock()
        for parameters in [dict(condition='unknown'),dict(condition='text_equals',element_id='e'),dict(condition='window_absent',window_id='w',element_id='e'),dict(condition='window_present',window_id='w',timeout=float('nan'))]:
            with self.subTest(parameters=parameters), self.assertRaises(DesktopError):
                desktop.wait_for(**parameters)
        desktop.list_windows.assert_not_called()

    def test_display_aliases_share_input_identity(self):
        aliases=[':1',':1.0',':1.2','unix/:1','unix:1','localhost:1','127.0.0.1:1','[::1]:1']
        self.assertEqual({display_identity(v) for v in aliases},{'local:1'})
        self.assertNotEqual(display_identity(':1'),display_identity(':2'))
        self.assertNotEqual(display_identity('remote:1'),display_identity(':1'))
