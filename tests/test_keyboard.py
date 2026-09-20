import ctypes
import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from luda._keyboard_native import Keyboard,State
from luda.common import DesktopError,operation_scope
from luda.desktop import Desktop
from luda.keyboard import send_chord,validate_chord,keyboard_capabilities,validate_key_count


class FakeKeyboard(Keyboard):
    def __init__(self):
        self.current=SimpleNamespace(base_mods=0,latched_mods=0,latched_group=0,group=0,locked_mods=0)
        self.keys=[];self.pointer=[]
        self.x=SimpleNamespace(root=1,_property=Mock(return_value=(33,32,[99],0)),window_tokens=lambda ids:{xid:'a'*32 for xid in ids})
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
    def test_desktop_passes_observed_window_generation_to_native_planner(self):
        from luda.desktop import Desktop
        desktop=Desktop();self.addCleanup(desktop.close)
        desktop.target_window=Mock(return_value={'xid':99,'window_id':'epoch:63:123:456:'+('a'*32)})
        with patch('luda.desktop.send_chord',return_value={'effect':'dispatched'}) as send:
            self.assertEqual(desktop.key('observed','Return')['effect'],'dispatched')
        send.assert_called_once_with('Return',99,target_generation='a'*32)

    def test_bounded_grammar(self):
        for chord in ('ctrl+s','ctrl+shift+v','Return','A','F24','super+alt+F1'):
            self.assertTrue(validate_chord(chord))
        for chord in (None,True,0,'','ctrl+ctrl+s','ctrl++s','Caps_Lock','Num_Lock','ctrl+hello','a b','a\n','F25','x'*65,'--clearmodifiers'):
            with self.subTest(chord=chord),self.assertRaises(DesktopError):validate_chord(chord)
    def test_repeat_bounds_before_any_helper(self):
        for count in (True,False,0,21,-1,1.0,'2',None):
            with self.subTest(count=count),patch('luda.keyboard.run') as run,self.assertRaises(DesktopError):send_chord('Down',99,count=count)
            run.assert_not_called()
        for count in (1,20):self.assertEqual(validate_key_count(count),count)
    def test_repeat_count_propagates_to_native_plan(self):
        import json
        with patch('luda.keyboard.run',return_value=b'{"code":"INPUT_HELD","message":"held"}') as run,self.assertRaises(DesktopError):send_chord('Down',99,count=4)
        self.assertEqual(json.loads(run.call_args.kwargs['data'])['count'],4)
        self.assertEqual(FakeKeyboard().plan('Return',99,count=20)['count'],20)
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
    def test_observed_target_token_required_before_mapping(self):
        keyboard=FakeKeyboard();keyboard.x._property.return_value=(31,8,b'b'*32,0)
        with self.assertRaises(DesktopError) as error:keyboard.plan('Return',99,'a'*32)
        self.assertEqual(error.exception.code,'STALE_TARGET')
        keyboard.x._property.return_value=None
        with self.assertRaises(DesktopError) as error:keyboard.plan('Return',99,'a'*32)
        self.assertEqual(error.exception.code,'STALE_TARGET')
    def test_press_identity_failure_always_ungrabs_without_down(self):
        keyboard=FakeKeyboard();keyboard.x.lib=Mock();keyboard.x.display=123
        keyboard.x._property.return_value=(31,8,b'b'*32,0);keyboard.event=Mock()
        with self.assertRaises(DesktopError):keyboard.press_target(36,99,'a'*32)
        keyboard.event.assert_not_called();keyboard.x.lib.XGrabServer.assert_called_once_with(123)
        keyboard.x.lib.XUngrabServer.assert_called_once_with(123);keyboard.x.lib.XSync.assert_called_once_with(123,False)
    def test_expected_token_is_passed_to_native_plan(self):
        with patch('luda.keyboard.run',return_value=b'{"code":"STALE_TARGET","message":"replaced"}') as run,self.assertRaises(DesktopError):send_chord('Return',99,target_generation='a'*32)
        import json
        self.assertEqual(json.loads(run.call_args.kwargs['data'])['target_generation'],'a'*32)
        with patch('luda.keyboard.run') as run,self.assertRaises(DesktopError):send_chord('Return',99,target_generation='invalid')
        run.assert_not_called()
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


class PendingKeyboardRecovery(unittest.TestCase):
    def test_recovery_retains_gate_before_resuming_stopped_guardian(self):
        import os,signal,subprocess,sys,time
        from luda import keyboard
        child=subprocess.Popen([sys.executable,'-c','import os,signal,json;os.kill(os.getpid(),signal.SIGSTOP);print(json.dumps({"done":True,"armed":True}))'],stdout=subprocess.PIPE)
        history=[];released=threading.Event()
        previous=(keyboard._retain_recovery,keyboard._release_recovery)
        def retain(token):history.append(('retained',token))
        def release(token):history.append(('released',token));released.set()
        try:
            deadline=time.monotonic()+2
            while time.monotonic()<deadline:
                from pathlib import Path
                if Path(f'/proc/{child.pid}/stat').read_text().rsplit(')',1)[1].split()[0]=='T':break
                time.sleep(.005)
            else:self.fail('owned fake guardian did not stop')
            keyboard.set_recovery_hooks(retain,release)
            keyboard._retain_guardian(child,b'')
            self.assertTrue(released.wait(3))
            self.assertEqual([item[0] for item in history],['retained','released'])
            self.assertEqual(history[0][1],history[1][1])
            keyboard.keyboard_recovery_checkpoint()
        finally:
            keyboard.set_recovery_hooks(*previous)
            if child.poll() is None:child.kill();child.wait(timeout=2)
            if not child.stdout.closed:child.stdout.close()
    def test_unverified_cleanup_cannot_reopen_input_gate(self):
        import subprocess,sys,time
        from luda import keyboard
        child=subprocess.Popen([sys.executable,'-c','import json;print(json.dumps(dict(armed=True,cleanup_verified=False,effect="uncertain")))'],stdout=subprocess.PIPE)
        retained=[];released=[];previous=(keyboard._retain_recovery,keyboard._release_recovery)
        try:
            keyboard.set_recovery_hooks(retained.append,released.append)
            keyboard._retain_guardian(child,b'')
            child.wait(timeout=2)
            time.sleep(.02)
            self.assertEqual(len(retained),1);self.assertEqual(released,[])
            with self.assertRaises(DesktopError) as error:keyboard.keyboard_recovery_checkpoint()
            self.assertEqual(error.exception.code,'BUSY')
            desktop=Desktop()
            try:
                with self.assertRaises(DesktopError):
                    with desktop.transaction():self.fail('Direct API passed unresolved keyboard recovery')
            finally:desktop.close()
        finally:
            keyboard.set_recovery_hooks(*previous)
            with keyboard._recovery_lock:
                for token in retained:keyboard._pending_recoveries.pop(token,None)
            if not child.stdout.closed:child.stdout.close()


if __name__=='__main__':unittest.main()
