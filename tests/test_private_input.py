import json
import unittest
from unittest.mock import Mock, patch

from luda._private_input import Binding, Devices, decode_token
from luda.private_input import PrivateInput
from luda.common import DesktopError


def token():
    return dict(name='luda-' + 'a' * 32, pointer=8, keyboard=9, generation='b' * 32)


class PrivateIdentityTest(unittest.TestCase):
    def test_strict_identity(self):
        good = token()
        self.assertEqual(decode_token(json.dumps(good)), good)
        for field, value in [('name', 'luda-other'), ('pointer', True), ('keyboard', 8),
                             ('generation', 'bad'), ('pointer', 2.5), ('pointer', 0)]:
            with self.subTest(field=field, value=value), self.assertRaises(DesktopError):
                decode_token(json.dumps({**good, field: value}))
        for raw in ['', 'null', '[]', '{}']:
            with self.subTest(raw=raw), self.assertRaises(DesktopError):
                decode_token(raw)

    def device_api(self):
        api = object.__new__(Devices)
        api.generation = Mock(return_value=token()['generation'])
        api.devices = Mock(return_value=[
            dict(id=8, name=token()['name'] + ' pointer', use=1, attachment=9, enabled=True),
            dict(id=9, name=token()['name'] + ' keyboard', use=2, attachment=8, enabled=True)])
        api.xi = Mock()
        api.x = Mock()
        return api

    def test_exact_pair_required(self):
        for field, value in [('name', 'unowned pointer'), ('use', 3), ('attachment', 3), ('enabled', False), ('id', 2)]:
            api = self.device_api()
            api.devices.return_value[0][field] = value
            with self.subTest(field=field), self.assertRaises(DesktopError):
                api.validate(token())
            self.assertFalse(api.remove(token()))
            api.xi.XIChangeHierarchy.assert_not_called()

    def test_server_restart_never_cleans_stale_ids(self):
        api = self.device_api()
        api.generation.return_value = 'c' * 32
        self.assertFalse(api.remove(token()))
        api.xi.XIChangeHierarchy.assert_not_called()

    def test_only_validated_pair_removed(self):
        api = self.device_api()
        self.assertTrue(api.remove(token()))
        api.xi.XIChangeHierarchy.assert_called_once()

    def test_generation_validation_is_read_only_and_never_ungrabs(self):
        api = object.__new__(Devices)
        api.x = Mock(root=1)
        api.x._property.return_value = (31, 8, b'b' * 32, 0)
        self.assertEqual(api.generation(), 'b' * 32)
        api.x.window_tokens.assert_not_called()
        api.x.lib.XGrabServer.assert_not_called()
        api.x.lib.XUngrabServer.assert_not_called()
        api.x._property.return_value = None
        with self.assertRaises(DesktopError):api.generation()
        api.x.window_tokens.assert_not_called()

    def test_remove_holds_server_lock_through_validation(self):
        api = self.device_api()
        order = []
        api.x.lib.XGrabServer.side_effect = lambda *_: order.append('grab')
        api.x.lib.XUngrabServer.side_effect = lambda *_: order.append('ungrab')
        api.generation.side_effect = lambda: (order.append('validate'), token()['generation'])[1]
        api.xi.XIChangeHierarchy.side_effect = lambda *_: order.append('remove')
        self.assertTrue(api.remove(token()))
        self.assertEqual(order, ['grab', 'validate', 'remove', 'ungrab'])

    def test_changed_client_pointer_refuses_input(self):
        binding = object.__new__(Binding)
        binding.devices = self.device_api()
        binding.token = token()
        binding.pointer = 8
        def selected(display, window, result):
            result._obj.value = 2
            return True
        binding.devices.xi.XIGetClientPointer.side_effect = selected
        with self.assertRaises(DesktopError):
            binding.validate()

    def test_owner_start_timeout_and_invalid_identity_close_child(self):
        for ready in [False, True]:
            process = Mock()
            process.poll.return_value = None
            with self.subTest(ready=ready), patch('luda.private_input.subprocess.Popen', return_value=process), \
                    patch('luda.private_input.select.select', return_value=([process.stdout] if ready else [], [], [])), \
                    patch('luda.private_input.os.read', return_value=b'{"error":"startup failed"}'):
                owner = PrivateInput({'DISPLAY': ':fixture'})
                with self.assertRaises(DesktopError):
                    owner.environment()
                process.stdin.close.assert_called_once()
                process.wait.assert_called_once()
                self.assertIsNone(owner._process)



if __name__ == '__main__':
    unittest.main()
