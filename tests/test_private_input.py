import json
import unittest
from unittest.mock import Mock

from luda._private_input import Devices, decode_token
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


if __name__ == '__main__':
    unittest.main()
