"""Compatibility selection precedes dispatch and stays fixed within an action."""
import unittest
from unittest.mock import Mock, patch
from luda.common import DesktopError, subprocess_environment
from luda.desktop import Desktop


class InputFallback(unittest.TestCase):
    def driver(self):
        desktop = Desktop.__new__(Desktop)
        desktop.environment = {'DISPLAY': ':fixture'}
        desktop.private_input = Mock()
        desktop.private_input.environment.return_value = {'DISPLAY': ':fixture', 'LUDA_PRIVATE_INPUT': 'owned'}
        return desktop

    def test_unknown_toolkit_uses_foreground_without_creating_devices(self):
        desktop = self.driver()
        with patch('luda.input_routing.prefers_private_input', return_value=False):
            with desktop.input_scope({'window_id':'window'}) as route:
                self.assertEqual(route, 'shared')
                self.assertEqual(subprocess_environment()['LUDA_INPUT_ROUTE'], 'shared')
                self.assertNotIn('LUDA_PRIVATE_INPUT', subprocess_environment())
        desktop.private_input.environment.assert_not_called()

    def test_supported_target_keeps_private_route_and_positive_cache(self):
        desktop = self.driver()
        with patch('luda.input_routing.prefers_private_input', return_value=True) as select, \
             patch('luda.desktop.keyboard_capabilities', return_value={'available':True}):
            for _ in range(2):
                with desktop.input_scope({'window_id':'window'}) as route:
                    self.assertEqual(route, 'private')
                    self.assertEqual(subprocess_environment()['LUDA_PRIVATE_INPUT'], 'owned')
            select.assert_called_once()

    def test_unavailable_private_pair_falls_back_before_dispatch(self):
        desktop = self.driver()
        with patch('luda.input_routing.prefers_private_input', return_value=True), \
             patch('luda.desktop.keyboard_capabilities', return_value={'available':False,'reason':'INPUT_UNAVAILABLE'}):
            with desktop.input_scope({'window_id':'window'}) as route:
                self.assertEqual(route, 'shared')
                self.assertNotIn('LUDA_PRIVATE_INPUT', subprocess_environment())

    def test_cancellation_and_session_change_never_choose_fallback(self):
        for code in ('CANCELLED', 'TIMEOUT', 'SESSION_CHANGED'):
            desktop = self.driver()
            desktop.private_input.environment.side_effect = DesktopError(code, 'stop')
            with self.subTest(code=code), patch('luda.input_routing.prefers_private_input', return_value=True):
                with self.assertRaises(DesktopError) as error:
                    with desktop.input_scope({'window_id':'window'}):
                        self.fail('must not dispatch')
                self.assertEqual(error.exception.code, code)

    def test_nested_composed_input_never_switches_routes(self):
        desktop = self.driver()
        with patch('luda.input_routing.prefers_private_input', side_effect=[False, True]) as select:
            with desktop.input_scope({'window_id':'window'}) as outer:
                with desktop.input_scope({'window_id':'window'}) as inner:
                    self.assertEqual((outer, inner), ('shared', 'shared'))
            select.assert_called_once()
        self.assertIsNone(desktop._input_route)

    def test_dispatched_or_uncertain_failure_is_never_replayed(self):
        desktop = self.driver()
        with patch('luda.input_routing.prefers_private_input', return_value=True), \
             patch('luda.desktop.keyboard_capabilities', return_value={'available':True}):
            with self.assertRaises(DesktopError):
                with desktop.input_scope({'window_id':'window'}) as route:
                    self.assertEqual(route, 'private')
                    raise DesktopError('BACKEND_ERROR', 'possibly dispatched', effect='uncertain')
        desktop.private_input.environment.assert_called_once()

    def test_shared_activation_refuses_held_human_input_first(self):
        desktop = self.driver()
        desktop.target_window = Mock(return_value={'xid':42, 'active':False})
        with patch('luda.desktop.keyboard_capabilities', return_value={'available':True,'input_held':True}), \
             patch('luda.desktop.run') as run, self.assertRaises(DesktopError) as error:
            desktop._activate_shared('window')
        self.assertEqual(error.exception.code, 'INPUT_HELD')
        run.assert_not_called()

    def test_shared_activation_revalidates_window_identity(self):
        desktop = self.driver()
        desktop.target_window = Mock(side_effect=[{'xid':42,'active':False},DesktopError('STALE_TARGET','replaced')])
        with patch('luda.desktop.keyboard_capabilities', return_value={'available':True}), \
             patch('luda.desktop.run'), self.assertRaises(DesktopError) as error:
            desktop._activate_shared('window')
        self.assertEqual(error.exception.code, 'STALE_TARGET')
        self.assertEqual(error.exception.effect, 'uncertain')

if __name__ == '__main__':
    unittest.main()
