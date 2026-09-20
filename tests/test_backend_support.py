"""Unsupported display backends must not reach GUI observation or mutation."""
from contextlib import nullcontext
import json
import os
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from luda import server
from luda._x11_helper import _NativeX11
from luda.common import DesktopError


class BackendSupport(unittest.TestCase):
    def test_pure_wayland_rejected_before_opening_x11(self):
        for environment in ({'WAYLAND_DISPLAY': 'wayland-0'}, {'XDG_SESSION_TYPE': 'wayland'}):
            with self.subTest(environment=environment), patch.dict(os.environ, environment, clear=True), patch('luda._x11_helper.C.CDLL') as library:
                with self.assertRaises(DesktopError) as caught:
                    _NativeX11()
                self.assertEqual((caught.exception.code, caught.exception.effect), ('UNSUPPORTED_BACKEND', 'none'))
                library.assert_not_called()

    def test_missing_display_does_not_guess_default_server(self):
        with patch.dict(os.environ, {}, clear=True), patch('luda._x11_helper.C.CDLL') as library:
            with self.assertRaises(DesktopError) as caught:
                _NativeX11()
            self.assertEqual(caught.exception.code, 'DISPLAY_UNAVAILABLE')
            library.assert_not_called()

    def test_xwayland_protocol_detection_needs_no_environment_hint(self):
        library = Mock()
        library.XOpenDisplay.return_value = 42
        library.XQueryExtension.return_value = 1
        with patch.dict(os.environ, {'DISPLAY': ':77'}, clear=True), patch('luda._x11_helper.C.CDLL', return_value=library):
            with self.assertRaises(DesktopError) as caught:
                _NativeX11()
        self.assertEqual(caught.exception.code, 'UNSUPPORTED_BACKEND')
        self.assertEqual(library.XQueryExtension.call_args.args[:2], (42, b'XWAYLAND'))
        library.XCloseDisplay.assert_called_once_with(42)
        library.XDefaultRootWindow.assert_not_called()

    def test_explicit_native_x11_target_is_not_rejected_by_unrelated_hints(self):
        library = Mock()
        library.XOpenDisplay.return_value = 42
        library.XQueryExtension.return_value = 0
        library.XDefaultRootWindow.return_value = 99
        with patch.dict(os.environ, {'DISPLAY': ':77', 'WAYLAND_DISPLAY': 'wayland-0', 'XDG_SESSION_TYPE': 'wayland'}, clear=True), patch('luda._x11_helper.C.CDLL', return_value=library):
            native = _NativeX11()
            self.assertEqual(native.root, 99)
            native.close()
        library.XCloseDisplay.assert_called_once_with(42)

    def test_server_refuses_before_handler_or_session_input(self):
        for method, arguments in [('observe', ()), ('list_windows', ()), ('key', ('old-window', 'Return')), ('element', ('old-element', 'invoke')), ('launch_application', ('application',))]:
            with self.subTest(method=method):
                handler = Mock()
                backend = SimpleNamespace(transaction=lambda: nullcontext(), control=Mock(), require_supported_backend=Mock(side_effect=DesktopError('UNSUPPORTED_BACKEND', 'Unsupported display.')))
                setattr(backend, method, handler)
                with patch.object(server, 'get_backend', return_value=backend), patch.object(server, 'require_session_input') as input_guard, patch.object(server, 'launch_application') as launch:
                    result = server.execute(method, *arguments)
                payload = json.loads(result.content[0].text)
                self.assertTrue(result.isError)
                self.assertEqual((payload['code'], payload['effect']), ('UNSUPPORTED_BACKEND', 'none'))
                handler.assert_not_called()
                launch.assert_not_called()
                input_guard.assert_not_called()
                self.assertFalse(server._operation_gate.locked())

    def test_diagnostics_remain_available_without_accepting_the_backend(self):
        backend = SimpleNamespace(transaction=lambda: nullcontext(), require_supported_backend=Mock(side_effect=AssertionError('Do not block diagnostics')), doctor=Mock(return_value={'ready': False, 'display_error_code': 'UNSUPPORTED_BACKEND'}))
        with patch.object(server, 'get_backend', return_value=backend):
            result = server.execute('doctor')
        self.assertFalse(result.isError)
        self.assertFalse(json.loads(result.content[0].text)['ready'])
        backend.require_supported_backend.assert_not_called()


if __name__ == '__main__':
    unittest.main()
