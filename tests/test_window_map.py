import ctypes as C
import unittest
from unittest.mock import Mock, patch
from luda._window_map import map_without_focus
from luda.common import DesktopError


class MapWithoutFocusTests(unittest.TestCase):
    def native(self):
        n = Mock()
        n.display = None
        n._property_atoms = {}
        n.window_tokens.side_effect = lambda ids: {i: 'generation' for i in ids}
        props = {(10, '_NET_WM_USER_TIME'): (6, 32, [123], 0),
                 (10, '_LUDA_WINDOW_TOKEN'): (31, 8, b'generation', 0)}
        n._property.side_effect = lambda w, key, size: props.get((w, key), (4, 32, [], 0) if key == '_NET_WM_STATE' else None)
        n.lib.XInternAtom.side_effect = lambda d, name, exists: 8 if name == b'_NET_WM_STATE_HIDDEN' else 9
        def change(d, w, atom, kind, fmt, mode, data, count):
            props[w, '_NET_WM_USER_TIME'] = (6, 32, [C.cast(data, C.POINTER(C.c_ulong))[0]], 0)
        n.lib.XChangeProperty.side_effect = change
        return n, props

    def test_restore_preserves_timestamp(self):
        n, props = self.native()
        self.assertEqual(map_without_focus(n, [10, 'generation'])['effect'], 'dispatched')
        self.assertEqual(props[10, '_NET_WM_USER_TIME'], (6, 32, [123], 0))
        n.lib.XMapWindow.assert_called_once_with(None, 10)

    def test_new_application_timestamp_is_not_overwritten(self):
        n, props = self.native()
        n.lib.XMapWindow.side_effect = lambda *args: props.update({(10, '_NET_WM_USER_TIME'): (6, 32, [456], 0)})
        map_without_focus(n, [10, 'generation'])
        self.assertEqual(props[10, '_NET_WM_USER_TIME'], (6, 32, [456], 0))

    def test_timeout_restores_timestamp(self):
        n, props = self.native()
        props[10, '_NET_WM_STATE'] = (4, 32, [8], 0)
        with patch('luda._window_map.time.monotonic', side_effect=[0, 2]), self.assertRaises(DesktopError) as caught:
            map_without_focus(n, [10, 'generation'])
        self.assertEqual(caught.exception.code, 'TIMEOUT')
        self.assertEqual(props[10, '_NET_WM_USER_TIME'], (6, 32, [123], 0))

    def test_stale_target_is_not_mapped(self):
        n, _ = self.native()
        with self.assertRaises(DesktopError):
            map_without_focus(n, [10, 'old'])
        n.lib.XMapWindow.assert_not_called()

    def test_identity_reuse_before_map_is_refused(self):
        n, props = self.native()
        props[10, '_LUDA_WINDOW_TOKEN'] = (31, 8, b'replaced', 0)
        with self.assertRaises(DesktopError):
            map_without_focus(n, [10, 'generation'])
        n.lib.XMapWindow.assert_not_called()
        self.assertEqual(props[10, '_NET_WM_USER_TIME'], (6, 32, [123], 0))

    def test_identity_reuse_during_restore_is_not_modified(self):
        n, props = self.native()
        n.lib.XMapWindow.side_effect = lambda *args: props.update({(10, '_LUDA_WINDOW_TOKEN'): (31, 8, b'replaced', 0)})
        with self.assertRaises(DesktopError):
            map_without_focus(n, [10, 'generation'])
        self.assertEqual(n.lib.XChangeProperty.call_count, 1)
        self.assertEqual(n.lib.XGrabServer.call_count, n.lib.XUngrabServer.call_count)

    def test_malformed_time_owner_is_not_mapped(self):
        n, props = self.native()
        props[10, '_NET_WM_USER_TIME_WINDOW'] = (31, 8, b'wrong', 0)
        with self.assertRaises(DesktopError):
            map_without_focus(n, [10, 'generation'])
        n.lib.XMapWindow.assert_not_called()
