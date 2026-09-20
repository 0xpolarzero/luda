import ctypes
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from luda._keyboard_native import Keyboard,State
from luda.common import DesktopError,operation_scope
from luda.desktop import Desktop
from luda.keyboard import send_chord,validate_chord,keyboard_capabilities


class FakeKeyboard(Keyboard):
    def __init__(self):
        self.current=SimpleNamespace(base_mods=0,latched_mods=0,latched_group=0,group=0,locked_mods=0)
        self.keys=[];self.pointer=[]
        self.x=SimpleNamespace(root=1,_property=Mock(return_value=(33,32,[99],0)))
    def state(self):return self.current
    def pressed(self):return self.keys
    def buttons(self):return self.pointer
    def modifier(self,name):return {'Control_L':(37,4),'Shift_L':(50,1),'Alt_L':(64,8),'Super_L':(133,64)}[name]
    def symbol(self,name):return ord(name) if len(name)==1 else 65293
    def lookup(self,code,mask,group):
        if code==36:return 65293
        if group:return None
        if code==38:return ord('A' if bool(mask&1)^bool(mask&2) else 'a')
        if code==10:return ord('1')
        return None


class KeyboardContract(unittest.TestCase):
    def test_bounded_grammar(self):
        for chord in ('ctrl+s','ctrl+shift+v','Return','A','F24','super+alt+F1'):
            self.assertTrue(validate_chord(chord))
        for chord in (None,True,0,'','ctrl+ctrl+s','ctrl++s','Caps_Lock','Num_Lock','ctrl+hello','a b','a\n','F25','x'*65,'--clearmodifiers'):
            with self.subTest(chord=chord),self.assertRaises(DesktopError):validate_chord(chord)
    def test_grammar_precedes_window_resolution(self):
        desktop=Desktop.__new__(Desktop);desktop.target_window=Mock()
        with self.assertRaises(DesktopError):desktop.key('unobserved','ctrl+ctrl+s')
        desktop.target_window.assert_not_called()
    def test_held_keys_and_extended_buttons_refused_before_plan(self):
        for kind in ('keys','pointer'):
            keyboard=FakeKeyboard();setattr(keyboard,kind,[8])
            with self.assertRaises(DesktopError) as error:keyboard.plan('Return',99)
            self.assertEqual(error.exception.code,'INPUT_HELD')
    def test_latched_state_refused(self):
        for field in ('latched_mods','latched_group'):
            keyboard=FakeKeyboard();setattr(keyboard.current,field,1)
            with self.assertRaises(DesktopError) as error:keyboard.plan('Return',99)
            self.assertEqual(error.exception.code,'UNSUPPORTED_INPUT_STATE')
    def test_focus_checked_in_native_preflight(self):
        with self.assertRaises(DesktopError) as error:FakeKeyboard().plan('Return',100)
        self.assertEqual(error.exception.code,'FOCUS_CHANGED')
    def test_case_planning_preserves_caps_lock(self):
        keyboard=FakeKeyboard()
        self.assertEqual(keyboard.plan('A',99)['keycodes'],[50,38])
        self.assertEqual(keyboard.plan('a',99)['keycodes'],[38])
        keyboard.current.locked_mods=2
        self.assertEqual(keyboard.plan('A',99)['keycodes'],[38])
        self.assertEqual(keyboard.plan('a',99)['keycodes'],[50,38])
        self.assertEqual(keyboard.plan('ctrl+a',99)['keycodes'],[37,38])
        self.assertEqual(keyboard.plan('ctrl+shift+a',99)['keycodes'],[37,50,38])
    def test_current_group_must_contain_symbol(self):
        keyboard=FakeKeyboard();keyboard.current.group=1
        with self.assertRaises(DesktopError) as error:keyboard.plan('a',99)
        self.assertEqual(error.exception.code,'UNSUPPORTED_KEYMAP')
        self.assertEqual(keyboard.plan('Return',99)['group'],1)
    def test_cancel_before_planning_spawns_nothing(self):
        event=threading.Event();event.set()
        with operation_scope(cancelled=event),patch('luda.keyboard.subprocess.Popen') as spawn,self.assertRaises(DesktopError) as error:send_chord('Return',99)
        self.assertEqual(error.exception.code,'CANCELLED');spawn.assert_not_called()
    def test_native_refusal_never_spawns_guardian(self):
        with patch('luda.keyboard.run',return_value=b'{"code":"INPUT_HELD","message":"held"}'),patch('luda.keyboard.subprocess.Popen') as spawn,self.assertRaises(DesktopError):send_chord('Return',99)
        spawn.assert_not_called()
    def test_target_grammar_before_helper(self):
        for xid in (True,0,-1,2**32,'99'):
            with patch('luda.keyboard.run') as run,self.assertRaises(DesktopError):send_chord('Return',xid)
            run.assert_not_called()
    def test_only_generation_matched_injector_is_disconnected(self):
        keyboard=Keyboard.__new__(Keyboard)
        keyboard.x=SimpleNamespace(lib=Mock(),display=1,_property=Mock(return_value=(31,8,b'a'*32,0)))
        keyboard.disconnect_injector({'xid':99,'generation':'b'*32})
        keyboard.x.lib.XKillClient.assert_not_called()
        keyboard.disconnect_injector({'xid':99,'generation':'a'*32})
        keyboard.x.lib.XKillClient.assert_called_once_with(1,99)
    def test_missing_injector_resource_is_harmless(self):
        keyboard=Keyboard.__new__(Keyboard)
        keyboard.x=SimpleNamespace(lib=Mock(),display=1,_property=Mock(side_effect=DesktopError('STALE_TARGET','gone')))
        keyboard.disconnect_injector({'xid':99,'generation':'a'*32})
        keyboard.x.lib.XKillClient.assert_not_called()
    def test_capability_probe_is_read_only_and_honest(self):
        with patch('luda.keyboard.run',return_value=b'{"available":true,"input_held":true}') as command:
            self.assertTrue(keyboard_capabilities()['input_held'])
            self.assertEqual(command.call_args.args[0][-1],'probe')
        with patch('luda.keyboard.run',return_value=b'{"code":"KEYBOARD_UNAVAILABLE"}'):
            self.assertFalse(keyboard_capabilities()['available'])
        with patch('luda.keyboard.run',side_effect=DesktopError('CANCELLED','test')),self.assertRaises(DesktopError):keyboard_capabilities()

    def test_state_layout_matches_xorg_header(self):
        self.assertEqual(State.locked_mods.offset,9)
        self.assertEqual(State.ptr_buttons.offset,16)
        self.assertEqual(ctypes.sizeof(State),18)


if __name__=='__main__':unittest.main()
