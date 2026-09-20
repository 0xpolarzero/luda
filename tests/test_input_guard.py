import json
import subprocess
import sys
import unittest
from unittest.mock import patch
from luda.common import DesktopError
from luda.input_guard import held_button


class InputGuardTests(unittest.TestCase):
    def test_invalid_button_never_spawns(self):
        with patch('luda.input_guard.subprocess.Popen') as spawn,self.assertRaises(DesktopError):
            with held_button('9'):pass
        spawn.assert_not_called()
    def test_held_input_refuses_before_guardian(self):
        with patch('luda.input_guard.run',return_value=b'{"code":"INPUT_HELD","message":"held"}'),patch('luda.input_guard.subprocess.Popen') as spawn,self.assertRaises(DesktopError):
            with held_button('1'):pass
        spawn.assert_not_called()
    def fake_guard(self,result):
        original=subprocess.Popen
        script='import sys,json;json.loads(sys.stdin.readline());print(json.dumps(dict(held=True)),flush=True);assert sys.stdin.read()=="D";print('+repr(json.dumps(result))+',flush=True)'
        return lambda args,**kwargs:original([sys.executable,'-c',script],**kwargs)
    def test_normal_release_awaits_owned_companion(self):
        with patch('luda.input_guard.run',return_value=b'{}') as plan,patch('luda.input_guard.subprocess.Popen',side_effect=self.fake_guard({'done':True,'cleanup_verified':True})):
            with held_button('1'):pass
        self.assertTrue(json.loads(plan.call_args.kwargs['data'])['hold'])
    def test_original_error_preserved_after_verified_cleanup(self):
        with patch('luda.input_guard.run',return_value=b'{}'),patch('luda.input_guard.subprocess.Popen',side_effect=self.fake_guard({'done':True,'cleanup_verified':True})),self.assertRaises(DesktopError) as caught:
            with held_button('1'):raise DesktopError('CANCELLED','test')
        self.assertEqual(caught.exception.code,'CANCELLED');self.assertTrue(caught.exception.details['cleanup_verified'])
    def test_unverified_release_retains_guardian_before_return(self):
        result={'code':'INPUT_RELEASE_UNVERIFIED','message':'unverified','armed':True,'effect':'uncertain','cleanup_verified':False}
        with patch('luda.input_guard.run',return_value=b'{}'),patch('luda.input_guard.subprocess.Popen',side_effect=self.fake_guard(result)),patch('luda.input_guard._retain_guardian') as retain,self.assertRaises(DesktopError) as caught:
            with held_button('1'):pass
        self.assertEqual(caught.exception.code,'INPUT_RELEASE_UNVERIFIED')
        retain.assert_called_once()
        guard,output,plan=retain.call_args.args
        self.assertEqual(json.loads(output)['cleanup_verified'],False)
        guard.wait(timeout=2);guard.stdout.close()
    def test_replacement_cleanup_is_explicit(self):
        result={'code':'SESSION_CHANGED','message':'replaced','session_changed':True,'cleanup_skipped':True,'cleanup_verified':False}
        with patch('luda.input_guard.run',return_value=b'{}'),patch('luda.input_guard.subprocess.Popen',side_effect=self.fake_guard(result)),self.assertRaises(DesktopError) as caught:
            with held_button('1'):pass
        self.assertEqual(caught.exception.code,'SESSION_CHANGED');self.assertTrue(caught.exception.details['cleanup_skipped'])

if __name__=='__main__':unittest.main()
