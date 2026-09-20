"""Do not discharge cleanup when part of the original private pair survives."""
import unittest
from unittest.mock import Mock, patch
from luda._private_cleanup import ended_ownership

class PrivateCleanup(unittest.TestCase):
    def test_surviving_owned_component_requires_normal_cleanup(self):
        for suffix in (' pointer', ' keyboard'):
            with self.subTest(suffix=suffix):
                token = {'name':'luda-'+'1'*32, 'generation':'2'*32}
                device = Mock()
                device.devices.return_value = [{'name':token['name']+suffix}]
                with patch('luda._private_cleanup._NativeX11') as native, \
                     patch('luda._private_cleanup.generation', return_value=token['generation']), \
                     patch('luda._private_cleanup.decode_token', return_value=token), \
                     patch('luda._private_cleanup.Devices', return_value=device), \
                     patch('luda._private_cleanup.disconnect_injector') as stop:
                    request = {'server_generation':token['generation'], 'client':{'xid':42}}
                    self.assertIsNone(ended_ownership(request))
                    stop.assert_called_once_with(native.return_value, request['client'])
                    native.return_value.close.assert_called_once()

    def test_replacement_never_disconnects_current_server_resource(self):
        with patch('luda._private_cleanup._NativeX11') as native, \
             patch('luda._private_cleanup.generation', return_value='new'), \
             patch('luda._private_cleanup.disconnect_injector') as stop:
            receipt = ended_ownership({'server_generation':'old', 'client':{'xid':42}})
            self.assertTrue(receipt['session_changed'])
            self.assertTrue(receipt['cleanup_skipped'])
            stop.assert_not_called()
            native.return_value.close.assert_called_once()

if __name__ == '__main__': unittest.main()
