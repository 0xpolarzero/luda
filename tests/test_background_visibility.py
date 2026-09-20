"""Only hidden top-levels qualify for a no-effect foreground retry."""
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from test_semantic import load_worker
from luda.common import DesktopError
from luda.desktop import Desktop


class BackgroundVisibility(unittest.TestCase):
    def test_worker_distinguishes_hidden_window_from_disabled_and_offscreen(self):
        worker = load_worker()
        target = {'root_path': '/root', 'path': '/field', 'root_bus_guid': 'a'*32,
                  'role': 'push button', 'name': 'Action', 'start': 'start'}
        root = SimpleNamespace(path='/root')
        field = SimpleNamespace(path='/field')
        cases = [(False, ['enabled'], True),
                 (False, [], False),
                 (True, ['enabled'], False),
                 (True, ['showing'], False)]
        for showing, states, fallback in cases:
            with self.subTest(showing=showing, states=states):
                current = {**target, 'states': states, 'protected': False}
                with patch.object(worker, 'candidates', return_value=iter([(root, 0), (field, 1)])), \
                     patch.object(worker, 'states_of', return_value=['showing'] if showing else []), \
                     patch.object(worker, 'describe', return_value=current), \
                     patch.object(worker, 'semantic') as dispatch:
                    result = worker.main({'op': 'invoke', 'pid': 1, 'target': target})
                self.assertEqual(result['error'], 'NOT_INTERACTABLE')
                self.assertEqual(result.get('foreground_required', False), fallback)
                dispatch.assert_not_called()

    def test_ax_preserves_only_explicit_boolean_foreground_refusal(self):
        for value in (True, False, None, 'true', 1):
            raw = json.dumps({'error': 'NOT_INTERACTABLE', 'foreground_required': value}).encode()
            with patch('luda.desktop.run', return_value=raw), self.assertRaises(DesktopError) as caught:
                Desktop.ax(Desktop.__new__(Desktop), {'op': 'invoke'}, True)
            self.assertEqual(caught.exception.effect, 'none')
            self.assertEqual(caught.exception.details.get('foreground_required', False), value is True)


if __name__ == '__main__':
    unittest.main()
