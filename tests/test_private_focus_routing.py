"""Routing never uses global activation for ordinary agent input."""
from contextlib import nullcontext
import unittest
from unittest.mock import Mock, patch
from luda.common import DesktopError
from luda.desktop import Desktop


class PrivateFocusRouting(unittest.TestCase):
    def driver(self):
        d = Desktop.__new__(Desktop)
        d.input_scope = Mock(side_effect=nullcontext)
        d.focus_input = Mock()
        d.check_input_focus = Mock()
        d.list_windows = Mock(return_value=[{'window_id': 'w:token', 'xid': 42, 'active': False}])
        d._raise_window = Mock(return_value={'effect': 'verified'})
        self.enterContext(patch('luda.interaction.properties', return_value=''))
        return d

    def test_private_focus_does_not_require_global_active(self):
        d = self.driver()
        self.assertEqual(d.target_window('w:token')['xid'], 42)
        d.check_input_focus.assert_called_once_with(d.list_windows.return_value[0])

    def test_no_global_activation_for_key(self):
        d = self.driver()
        with patch('luda.desktop.send_chord', return_value={'effect': 'dispatched'}) as send, patch('luda.desktop.run') as run:
            d.key('w:token', 'Return')
        d.focus_input.assert_called_once()
        send.assert_called_once_with('Return', 42, target_generation='token', count=1)
        d._raise_window.assert_not_called()
        run.assert_not_called()

    def test_composed_key_does_not_reacquire_lost_private_focus(self):
        d = self.driver()
        d.check_input_focus.side_effect = DesktopError('FOCUS_CHANGED', 'private focus lost')
        with patch('luda.desktop.send_chord') as send, self.assertRaises(DesktopError):
            d.key('w:token', 'Return', _activate=False)
        d.focus_input.assert_not_called()
        send.assert_not_called()

    def test_explicit_activate_raises_and_sets_only_private_focus(self):
        d = self.driver()
        with patch('luda.desktop.run') as run:
            result = d.activate('w:token')
        self.assertEqual(result['effect'], 'verified')
        d._raise_window.assert_called_once()
        d.focus_input.assert_called_once()
        run.assert_not_called()

    def test_failed_raise_does_not_claim_focus_success(self):
        d = self.driver()
        d._raise_window.return_value = {'effect': 'dispatched'}
        self.assertEqual(d.activate('w:token')['effect'], 'dispatched')
        d.focus_input.assert_not_called()

    def test_stale_target_does_not_focus(self):
        d = self.driver()
        d.list_windows.return_value = []
        with self.assertRaises(DesktopError) as caught:
            d.key('w:token', 'Return')
        self.assertEqual(caught.exception.code, 'STALE_TARGET')
        d.focus_input.assert_not_called()
