"""Explicit compatibility routing must not weaken private ownership contracts."""
import unittest
import json
from types import SimpleNamespace
from unittest.mock import Mock, patch
from luda._private_input import SharedBinding, bind_private_input, validate_route, ROUTE_ENV
from luda._private_cleanup import ended_ownership
from luda._keyboard_guard import cleanup_request
from luda.common import DesktopError
from test_keyboard import FakeKeyboard


class SharedInput(unittest.TestCase):
    def api(self):
        native=Mock(root=1,display=7)
        devices=Mock()
        devices.x=native
        devices.generation.return_value='a'*32
        devices.devices.return_value=[
            dict(id=2,name='Virtual core pointer',use=1,attachment=3,enabled=True),
            dict(id=3,name='Virtual core keyboard',use=2,attachment=2,enabled=True)]
        def get(display,window,selected):selected._obj.value=2;return True
        devices.xi.XIGetClientPointer.side_effect=get
        return native,devices

    def test_explicit_route_only(self):
        with patch.dict('os.environ',{},clear=True), patch('luda._private_input.SharedBinding') as shared:
            with self.assertRaises(DesktopError):bind_private_input(Mock())
            shared.assert_not_called()
        with patch.dict('os.environ',{ROUTE_ENV:'shared'},clear=True), patch('luda._private_input.SharedBinding') as shared:
            self.assertIs(bind_private_input(Mock()),shared.return_value)
        with patch.dict('os.environ',{ROUTE_ENV:'guess'},clear=True), self.assertRaises(DesktopError):
            bind_private_input(Mock())

    def test_shared_connection_does_not_rebind_devices(self):
        native,devices=self.api()
        with patch('luda._private_input.Devices',return_value=devices):binding=SharedBinding(native)
        self.assertEqual((binding.pointer,binding.keyboard),(2,3))
        devices.xi.XISetClientPointer.assert_not_called()
        devices.xi.XISetFocus.assert_not_called()
        devices.xi.XIChangeHierarchy.assert_not_called()

    def test_changed_pair_or_generation_blocks_shared_events(self):
        for changed in ('pair','generation','connection'):
            with self.subTest(changed=changed):
                native,devices=self.api()
                with patch('luda._private_input.Devices',return_value=devices):binding=SharedBinding(native)
                if changed=='pair':devices.devices.return_value[1]['attachment']=8
                if changed=='generation':devices.generation.return_value='b'*32
                if changed=='connection':devices.xi.XIGetClientPointer.side_effect=lambda *_:False
                with self.assertRaises(DesktopError):binding.validate()

    def test_shared_route_refuses_noncore_default_pair(self):
        native,devices=self.api()
        devices.devices.return_value[0]['name']='another pointer'
        with patch('luda._private_input.Devices',return_value=devices),self.assertRaises(DesktopError):SharedBinding(native)

    def test_shared_focus_checks_foreground_and_never_changes_it(self):
        keyboard=FakeKeyboard();keyboard.private.route='shared'
        keyboard.target_token=Mock(return_value='a'*32)
        keyboard.focus_target(99,'a'*32)
        keyboard.private.focus.assert_not_called()
        keyboard.x._property.return_value=(33,32,[100],0)
        with self.assertRaises(DesktopError):keyboard.focus_target(99,'a'*32)
        keyboard.private.focus.assert_not_called()

    def test_cleanup_route_is_pinned_and_checked_before_disconnect(self):
        plan=dict(input_route='shared',server_generation='a'*32,keycodes=[38])
        request=cleanup_request(plan,{'xid':42,'generation':'b'*32})
        self.assertEqual(request['input_route'],'shared')
        with patch.dict('os.environ',{ROUTE_ENV:'private'},clear=True), \
                patch('luda._private_cleanup.disconnect_injector') as stop, self.assertRaises(DesktopError):ended_ownership(request)
        stop.assert_not_called()
        with patch.dict('os.environ',{ROUTE_ENV:'shared'},clear=True), \
                patch('luda._private_cleanup._NativeX11'), \
                patch('luda._private_cleanup.generation',return_value='a'*32), \
                patch('luda._private_cleanup.disconnect_injector'), \
                patch('luda._private_cleanup.decode_token') as decode:
            self.assertIsNone(ended_ownership(request))
            decode.assert_not_called()
        with patch.dict('os.environ',{ROUTE_ENV:'shared'},clear=True),self.assertRaises(DesktopError):validate_route({})

    def test_private_owner_overrides_inherited_shared_route(self):
        from luda.private_input import PrivateInput
        from luda._private_input import TOKEN_ENV
        token=dict(name='luda-'+'a'*32,pointer=8,keyboard=9,generation='b'*32)
        process=Mock();process.poll.return_value=None
        with patch('luda.private_input.subprocess.Popen',return_value=process) as spawn, \
                patch('luda.private_input.select.select',return_value=([process.stdout],[],[])), \
                patch('luda.private_input.os.read',return_value=json.dumps(token).encode()):
            owner=PrivateInput({ROUTE_ENV:'shared',TOKEN_ENV:'stale','DISPLAY':':fixture'})
            env=owner.environment()
            self.assertEqual(env[ROUTE_ENV],'private')
            self.assertEqual(json.loads(env[TOKEN_ENV]),token)
            self.assertNotIn(ROUTE_ENV,spawn.call_args.kwargs['env'])
            self.assertNotIn(TOKEN_ENV,spawn.call_args.kwargs['env'])
            owner.close()

    def test_shared_cleanup_server_restart_skips_disconnection(self):
        request=dict(input_route='shared',server_generation='a'*32,client={'xid':42})
        with patch.dict('os.environ',{ROUTE_ENV:'shared'},clear=True), \
                patch('luda._private_cleanup._NativeX11'), \
                patch('luda._private_cleanup.generation',return_value='b'*32), \
                patch('luda._private_cleanup.disconnect_injector') as stop:
            result=ended_ownership(request)
        self.assertTrue(result['session_changed']);stop.assert_not_called()


if __name__=='__main__':unittest.main()
