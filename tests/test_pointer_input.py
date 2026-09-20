import json
import unittest
from unittest.mock import patch,Mock
from test_keyboard import FakeKeyboard
from luda._pointer_native import plan_pointer,move_pointer as native_move,target_guard
from luda._keyboard_guard import cleanup_request, native_module
from luda.common import DesktopError
from luda.pointer_input import click_button,check_pointer_ready


class PointerContract(unittest.TestCase):
    def test_invalid_arguments_never_start_helper(self):
        cases=[(True,1,None),(1,1,None),('8',1,None),('1',True,None),('1',0,None),('1',21,None),('1',1,True),('1',1,0)]
        for button,count,target in cases:
            with self.subTest(case=(button,count,target)),patch('luda.pointer_input.run') as run,self.assertRaises(DesktopError):
                click_button(button,count,target)
            run.assert_not_called()
    def test_readiness_refuses_before_caller_movement(self):
        with patch('luda.pointer_input.run',return_value=b'{"code":"INPUT_HELD","message":"held"}'),self.assertRaises(DesktopError):check_pointer_ready(99)
        with patch('luda.pointer_input.run',return_value=b'{"server_generation":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}') as run:
            self.assertEqual(check_pointer_ready()['effect'],'none')
        self.assertEqual(json.loads(run.call_args.kwargs['data'])['target'],None)
    def test_motion_requires_original_generation_and_owned_button(self):
        request={'position':[10,20],'server_generation':'a'*32,'held_button':'1'}
        native=FakeKeyboard();native.x.lib=Mock();native.x.display=1
        with patch('luda._pointer_native.motion') as motion:
            for buttons in ([],[2],[1,2]):
                native.pointer=buttons
                with self.assertRaises(DesktopError) as error:native_move(native,request)
                self.assertEqual(error.exception.code,'INPUT_HELD')
            native.pointer=[1]
            native_move(native,request);motion.assert_called_once_with(native,[10,20]);motion.reset_mock()
            with self.assertRaises(DesktopError) as error:native_move(native,dict(request,server_generation='b'*32))
            self.assertEqual(error.exception.code,'SESSION_CHANGED');motion.assert_not_called()
    def test_combined_click_validates_position_before_dispatch(self):
        for position in ((True,2),(-1,2),(1,),[1,2,3],(1.5,2),(32768,0)):
            with patch('luda.pointer_input.run') as run,self.assertRaises(DesktopError):click_button('1',position=position)
            run.assert_not_called()
        native=FakeKeyboard();native.x.geometry=lambda xid:{'width':100,'height':100}
        with self.assertRaises(DesktopError) as error:plan_pointer(native,{'button':'1','count':1,'position':[100,0]})
        self.assertEqual(error.exception.code,'OUT_OF_BOUNDS')
        plan=plan_pointer(native,{'button':'1','count':1,'position':[99,0],'server_generation':'a'*32})
        self.assertEqual(plan['position'],[99,0])
        with self.assertRaises(DesktopError) as error:plan_pointer(native,dict(plan,server_generation='b'*32))
        self.assertEqual(error.exception.code,'SESSION_CHANGED')
    def test_ended_hold_cannot_move(self):
        from luda.input_guard import HeldPointer
        pointer=HeldPointer('1','a'*32);pointer.active=False
        with patch('luda.input_guard._move_pointer') as move,self.assertRaises(DesktopError):pointer.move(10,20)
        move.assert_not_called()
    def test_held_keys_and_buttons_refuse(self):
        for attribute in ('keys','pointer'):
            native=FakeKeyboard();setattr(native,attribute,[8])
            with self.assertRaises(DesktopError) as error:plan_pointer(native,{'button':'4','count':2,'target':99})
            self.assertEqual(error.exception.code,'INPUT_HELD')
    def test_observed_pointer_token_refused_before_motion_and_ungrabbed(self):
        native=FakeKeyboard();native.x.lib=Mock();native.x.display=1
        native.x._property.return_value=(31,8,b'b'*32,0)
        with patch('luda._pointer_native.motion') as motion,self.assertRaises(DesktopError) as error:
            native_move(native,{'position':[1,2],'server_generation':'a'*32,'target':99,'target_generation':'a'*32})
        self.assertEqual(error.exception.code,'STALE_TARGET');motion.assert_not_called()
        with self.assertRaises(DesktopError):
            with target_guard(native,99,'a'*32):self.fail('reused target entered')
        native.x.lib.XUngrabServer.assert_called_once_with(1)
    def test_public_calls_propagate_observed_pointer_token(self):
        from luda.pointer_input import move_pointer
        from luda.input_guard import held_button
        calls=[lambda:click_button('1',target=99,target_generation='a'*32),lambda:check_pointer_ready(99,target_generation='a'*32),lambda:move_pointer(1,2,'b'*32,target=99,target_generation='a'*32)]
        for call in calls:
            with patch('luda.pointer_input.run',return_value=b'{"code":"STALE_TARGET","message":"replaced"}') as run,self.assertRaises(DesktopError):call()
            self.assertEqual(json.loads(run.call_args.kwargs['data'])['target_generation'],'a'*32)
        with patch('luda.input_guard.run',return_value=b'{"code":"STALE_TARGET","message":"replaced"}') as run,self.assertRaises(DesktopError):
            with held_button('1',target=99,target_generation='a'*32):pass
        self.assertEqual(json.loads(run.call_args.kwargs['data'])['target_generation'],'a'*32)
    def test_target_generation_requires_valid_bound_target(self):
        for target,token in ((None,'a'*32),(99,'broken')):
            with patch('luda.pointer_input.run') as run,self.assertRaises(DesktopError):click_button('1',target=target,target_generation=token)
            run.assert_not_called()
    def test_focus_change_refuses(self):
        with self.assertRaises(DesktopError) as error:plan_pointer(FakeKeyboard(),{'button':'1','count':1,'target':100})
        self.assertEqual(error.exception.code,'FOCUS_CHANGED')
    def test_latched_state_refuses_but_locks_preserved(self):
        native=FakeKeyboard();native.current.locked_mods=18
        plan=plan_pointer(native,{'button':'7','count':20,'target':99})
        self.assertEqual(plan['server_generation'],'a'*32)
        self.assertEqual(native.current.locked_mods,18)
        native.current.latched_mods=1;native.x._property.return_value=(31,8,b'a'*32,0)
        with self.assertRaises(DesktopError) as error:plan_pointer(native,plan)
        self.assertEqual(error.exception.code,'UNSUPPORTED_INPUT_STATE')
    def test_refusal_never_dispatches(self):
        with patch('luda.pointer_input.run',return_value=b'{"code":"INPUT_HELD","message":"held"}'),patch('luda.pointer_input._dispatch_plan') as dispatch,self.assertRaises(DesktopError):click_button('1',1,99)
        dispatch.assert_not_called()
    def test_guardian_and_recovery_keep_button_ownership(self):
        plan={'kind':'pointer','button':'5','count':3,'target':99,'server_generation':'a'*32}
        client={'xid':123,'generation':'b'*32}
        self.assertEqual(native_module(plan),'luda._pointer_native')
        self.assertEqual(cleanup_request(plan,client),{'kind':'pointer','button':'5','client':client,'server_generation':'a'*32})
        with patch('luda.pointer_input.run',return_value=json.dumps(plan).encode()),patch('luda.pointer_input._dispatch_plan',return_value={'effect':'dispatched'}) as dispatch:
            self.assertEqual(click_button('5',3,99),{'effect':'dispatched'})
        dispatch.assert_called_once_with(plan)


if __name__=='__main__':unittest.main()
