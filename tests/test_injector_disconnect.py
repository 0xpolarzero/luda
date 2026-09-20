"""Nonce validation and disconnect must exclude same-server XID reassignment."""
import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from luda._keyboard_native import Keyboard
from luda.common import DesktopError

class InjectorDisconnect(unittest.TestCase):
    def setUp(self):
        self.events=[];self.grabbed=False
        def grab(_):self.grabbed=True;self.events.append('grab')
        def ungrab(_):self.grabbed=False;self.events.append('ungrab')
        def kill(*_):
            self.assertTrue(self.grabbed,'An unrelated client could reuse the verified XID before kill')
            self.events.append('kill')
        self.lib=SimpleNamespace(XGrabServer=Mock(side_effect=grab),XUngrabServer=Mock(side_effect=ungrab),XKillClient=Mock(side_effect=kill),XSync=Mock(side_effect=lambda *_:self.events.append('sync')))
        self.keyboard=Keyboard.__new__(Keyboard)
        self.keyboard.x=SimpleNamespace(display=1,lib=self.lib,_property=self.property)
    def property(self,*_):
        self.assertTrue(self.grabbed,'Nonce must be read under the same grab as disconnect')
        self.events.append('nonce')
        return (31,8,b'a'*32,0)
    def test_verified_disconnect_holds_grab_until_kill_processed(self):
        self.keyboard.disconnect_injector({'xid':99,'generation':'a'*32})
        self.assertEqual(self.events,['grab','nonce','kill','sync','ungrab','sync'])
        self.assertFalse(self.grabbed)
    def test_reused_resource_never_killed_and_grab_released(self):
        self.keyboard.disconnect_injector({'xid':99,'generation':'b'*32})
        self.assertEqual(self.events,['grab','nonce','ungrab','sync'])
    def test_provider_failure_and_disappearance_always_release_grab(self):
        for code in ('STALE_TARGET','INVALID_WINDOW_TOKEN'):
            self.events.clear()
            self.keyboard.x._property=Mock(side_effect=DesktopError(code,'private'))
            if code=='STALE_TARGET':self.keyboard.disconnect_injector({'xid':99,'generation':'a'*32})
            else:
                with self.assertRaises(DesktopError):self.keyboard.disconnect_injector({'xid':99,'generation':'a'*32})
            self.assertEqual(self.events,['grab','ungrab','sync']);self.assertFalse(self.grabbed)

if __name__=='__main__':unittest.main()
