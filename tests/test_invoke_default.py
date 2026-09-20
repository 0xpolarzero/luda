import unittest
from unittest.mock import Mock
from luda.common import DesktopError
from luda.desktop import Desktop
from luda.timing import elapsed_time

class InvokeDefault(unittest.TestCase):
    def desktop(self,actions):
        d=Desktop.__new__(Desktop)
        d.elements={'element':{'time':elapsed_time(),'window_id':'window','node':{'start':'start','actions':actions}}}
        d.target_window=Mock(return_value={'pid':123,'start':'start'})
        d.ax=Mock(return_value={'effect':'dispatched'})
        return d
    def test_sole_observed_provider_action_is_used_without_guessing(self):
        for name in ('click','press','activate','custom operation'):
            d=self.desktop([name])
            self.assertEqual(d.element('element','invoke')['effect'],'dispatched')
            self.assertEqual(d.ax.call_args.args[0]['action'],name)
    def test_multiple_actions_require_explicit_choice_before_worker(self):
        d=self.desktop(['open','delete'])
        with self.assertRaises(DesktopError) as error:d.element('element','invoke')
        self.assertEqual(error.exception.code,'ACTION_REQUIRED')
        self.assertEqual(error.exception.effect,'none');d.ax.assert_not_called()
        d.element('element','invoke',action='open')
        self.assertEqual(d.ax.call_args.args[0]['action'],'open')
    def test_no_action_does_not_guess_click(self):
        d=self.desktop([])
        with self.assertRaises(DesktopError) as error:d.element('element','invoke')
        self.assertEqual(error.exception.code,'UNSUPPORTED_ACTION');d.ax.assert_not_called()
    def test_unobserved_action_cannot_be_selected(self):
        for value in ('press','',True,1,[]):
            d=self.desktop(['click'])
            with self.assertRaises(DesktopError):d.element('element','invoke',action=value)
            d.ax.assert_not_called()
    def test_null_defaults_but_duplicate_actions_remain_ambiguous(self):
        d=self.desktop(['activate']);d.element('element','invoke',action=None)
        self.assertEqual(d.ax.call_args.args[0]['action'],'activate')
        d=self.desktop(['activate','activate'])
        with self.assertRaises(DesktopError) as error:d.element('element','invoke')
        self.assertEqual(error.exception.code,'ACTION_REQUIRED');d.ax.assert_not_called()
