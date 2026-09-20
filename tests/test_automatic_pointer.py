"""Automatic activation must preserve screenshot identity and no-input guards."""
import copy
import unittest
from unittest.mock import Mock, patch

from luda.common import DesktopError
from luda.desktop import Desktop


class AutomaticPointerTests(unittest.TestCase):
    def driver(self):
        d = Desktop(environment={})
        self.addCleanup(d.close)
        target = {'window_id': 'target', 'xid': 10, 'active': False,
                  'bounds': {'x': 10, 'y': 20, 'width': 200, 'height': 100}, 'workspace': 0}
        human = {'window_id': 'human', 'xid': 20, 'active': True,
                 'bounds': {'x': 300, 'y': 20, 'width': 200, 'height': 100}, 'workspace': 0}
        windows = [target, human]
        d.target_window = Mock(return_value=target)
        d.list_windows = Mock(side_effect=lambda: windows)
        topology = {'server_generation': 'generation'}
        d.display = Mock(return_value=Mock(topology=Mock(return_value=topology)))
        d.observe_popups = Mock(return_value=[])
        d.snapshots = {'original': {'signature': d.signature(windows), 'topology': topology, 'popups': []}}
        d._interaction_point = Mock(return_value=(15, 25))
        def activate(*_):
            target['active'] = True
            human['active'] = False
        d.activate = Mock(side_effect=activate)
        d.cursor = Mock()
        return d, target, windows

    @patch('luda.interaction.check_pointer_ready', return_value={'server_generation': 'generation'})
    def test_only_internal_snapshot_allows_our_activation(self, ready):
        d, target, windows = self.driver()
        before = copy.deepcopy(d.snapshots['original'])
        with d.pointer_action('target', 'original', [('target', 1, 2)]) as token:
            self.assertNotEqual(token, 'original')
            self.assertEqual(d.snapshots[token]['signature'], d.signature(windows))
            self.assertEqual(d.snapshots['original'], before)
            self.assertTrue(target['active'])
        self.assertEqual(d.snapshots, {'original': before})
        d._interaction_point.assert_called_once_with('target', 'original', 1, 2, False)
        d.cursor.hide.assert_called_once()
        d.activate.assert_called_once_with('target')
        ready.assert_called_once_with()

    @patch('luda.interaction.check_pointer_ready')
    def test_bad_point_never_activates_or_checks_input(self, ready):
        for code in ('STALE_OBSERVATION', 'OCCLUDED_TARGET', 'OUT_OF_BOUNDS'):
            d, _, _ = self.driver()
            d._interaction_point.side_effect = DesktopError(code, 'invalid')
            with self.assertRaises(DesktopError) as caught:
                with d.pointer_action('target', 'original', [('target', 1, 2)]):
                    self.fail('invalid point authorized')
            self.assertEqual(caught.exception.effect, 'none')
            d.activate.assert_not_called()
        ready.assert_not_called()

    @patch('luda.interaction.check_pointer_ready')
    def test_held_input_and_server_change_do_not_activate(self, ready):
        d, _, _ = self.driver()
        for result in (DesktopError('INPUT_HELD', 'held'), {'server_generation': 'replacement'}):
            ready.side_effect = result if isinstance(result, Exception) else None
            ready.return_value = result
            with self.assertRaises(DesktopError):
                with d.pointer_action('target', 'original', [('target', 1, 2)]):
                    self.fail('invalid input authorized')
            d.activate.assert_not_called()

    @patch('luda.interaction.check_pointer_ready', return_value={'server_generation': 'generation'})
    def test_layout_popup_and_topology_change_never_reach_input(self, ready):
        for change in ('geometry', 'workspace', 'identity', 'popup', 'topology'):
            d, target, _ = self.driver()
            activate = d.activate.side_effect
            def changed(*args):
                activate(*args)
                if change == 'geometry': target['bounds']['x'] += 1
                elif change == 'workspace': target['workspace'] += 1
                elif change == 'identity': target['window_id'] = 'replacement'
                elif change == 'popup': d.observe_popups.side_effect = DesktopError('STALE_OBSERVATION', 'new popup')
                elif change == 'topology': d.display().topology.return_value = {'server_generation': 'other'}
            d.activate.side_effect = changed
            # Signature captures bounds by reference in production; snapshot's
            # bounds are separate objects from subsequent metadata observations.
            d.snapshots = copy.deepcopy(d.snapshots)
            with self.subTest(change=change), self.assertRaises(DesktopError) as caught:
                with d.pointer_action('target', 'original', [('target', 1, 2)]):
                    self.fail('changed layout authorized')
            self.assertEqual(caught.exception.code, 'STALE_OBSERVATION')
            self.assertEqual(caught.exception.effect, 'uncertain')  # Activation already happened.
            self.assertEqual(list(d.snapshots), ['original'])

    @patch('luda.interaction.check_pointer_ready', return_value={'server_generation': 'generation'})
    def test_timeout_does_not_retry_and_temporary_snapshot_is_removed(self, ready):
        d, _, _ = self.driver()
        with self.assertRaises(DesktopError) as caught:
            with d.pointer_action('target', 'original', [('target', 1, 2)]):
                raise DesktopError('TIMEOUT', 'input completion unknown', effect='uncertain')
        self.assertEqual(caught.exception.code, 'TIMEOUT')
        self.assertEqual(list(d.snapshots), ['original'])
        d.activate.assert_called_once()

    @patch('luda.interaction.check_pointer_ready')
    def test_active_target_does_not_activate(self, ready):
        d, target, _ = self.driver()
        target['active'] = True
        with d.pointer_action('target', 'original', [('target', 1, 2)]) as token:
            self.assertEqual(token, 'original')
        d.activate.assert_not_called()
        ready.assert_not_called()

    def test_invalid_pointer_options_do_not_activate(self):
        d, _, _ = self.driver()
        for options in ({'button': 'bad'}, {'count': 0}, {'kind': 'bad'}, {'direction': 'bad'}):
            with self.assertRaises(DesktopError):
                d.pointer('target', 'original', 1, 2, **options)
        d.activate.assert_not_called()
        d.cursor.hide.assert_not_called()

    def test_renderer_failure_cannot_turn_input_into_a_retry(self):
        d, _, _ = self.driver()
        d.environment = {'DISPLAY': ':99'}
        d.cursor.show.side_effect = RuntimeError('renderer gone')
        d.agent_feedback('target', position=(10, 20))
        d.cursor.show.assert_called_once()

    @patch('luda.interaction.run')
    def test_semantic_marker_uses_fresh_geometry_not_cached_inspection(self, run):
        d, target, _ = self.driver()
        d.environment = {'DISPLAY': ':99'}
        target.update(pid=42, start='process')
        d.elements['e'] = {'node': {'bounds': {'x': 1, 'y': 2, 'width': 4, 'height': 6}}}
        run.return_value = b'{"bounds":{"x":100,"y":200,"width":20,"height":40}}'
        d.agent_feedback('target', element_id='e')
        d.cursor.show.assert_called_once_with(110, 220, kind='action')
        self.assertEqual(run.call_args.kwargs['timeout'], .4)

    @patch('luda.interaction.run', side_effect=DesktopError('TIMEOUT', 'geometry unavailable'))
    def test_missing_geometry_degrades_to_current_window_marker(self, run):
        d, target, _ = self.driver()
        d.environment = {'DISPLAY': ':99'}
        target.update(pid=42, start='process')
        d.elements['e'] = {'node': {'bounds': {'x': 1, 'y': 2, 'width': 4, 'height': 6}}}
        d.agent_feedback('target', element_id='e')
        d.cursor.show.assert_called_once_with(110, 70, kind='action')


if __name__ == '__main__':
    unittest.main()
