import json
import unittest
from unittest.mock import Mock,patch
from luda import keyboard
from luda.common import DesktopError,environment_scope,subprocess_environment


class InputRecovery(unittest.TestCase):
    def setUp(self):
        self.guard=Mock();self.guard.poll.return_value=0
        self.release=Mock()
        self.record={'guard':self.guard,'output':b'','plan':{'server_generation':'a'*32},
                     'environment':{'DISPLAY':':original'},'release':self.release,
                     'cleanup_request':{'server_generation':'a'*32,'keycodes':[37], 'client':{'xid':9,'generation':'b'*32}}}
        self.token='test-input-generation'
        with keyboard._recovery_lock:keyboard._pending_recoveries[self.token]=self.record
        self.addCleanup(self.clear)
    def clear(self):
        with keyboard._recovery_lock:keyboard._pending_recoveries.pop(self.token,None)
    def test_replacement_proof_never_releases_new_server_keys(self):
        with patch('luda.keyboard.run',return_value=b'{"session_changed":true,"cleanup_skipped":true}') as run:
            result=keyboard.recover_keyboard_input()
        self.assertEqual(result['pending_count'],0)
        self.assertEqual(result['resolved_count'],1)
        self.assertEqual(run.call_count,1)
        self.assertEqual(json.loads(run.call_args.kwargs['data'])['operation'],'check')
        self.release.assert_called_once_with(self.token)
    def test_same_server_cleanup_uses_original_environment_only(self):
        calls=[]
        def run(args,**kwargs):
            calls.append((args,dict(subprocess_environment()),json.loads(kwargs['data'])))
            return b'{"session_changed":false}' if len(calls)==1 else b'{"released":true}'
        with environment_scope({'DISPLAY':':new-backend'}),patch('luda.keyboard.run',side_effect=run):
            result=keyboard.recover_keyboard_input()
            self.assertEqual(subprocess_environment()['DISPLAY'],':new-backend')
        self.assertEqual(result['pending_count'],0)
        self.assertEqual([item[1] for item in calls],[{'DISPLAY':':original'}]*2)
        self.assertEqual(calls[1][0][-1],'release')
    def test_pointer_recovery_reports_button_proof(self):
        self.record['cleanup_request'].update(kind='pointer',button='1')
        with patch('luda.keyboard.run',side_effect=[b'{"session_changed":false}',b'{"released":true}']) as run:
            result=keyboard.recover_keyboard_input()
        self.assertEqual(result['recoveries'][0]['proof'],'owned_buttons_released')
        self.assertIn('luda._pointer_native',run.call_args.args[0])
    def test_failed_cleanup_remains_blocked(self):
        with patch('luda.keyboard.run',side_effect=[b'{"session_changed":false}',b'{"released":false}']):result=keyboard.recover_keyboard_input()
        self.assertEqual(result['pending_count'],1)
        self.release.assert_not_called()
        with self.assertRaises(DesktopError):keyboard.keyboard_recovery_checkpoint()
    def test_dead_server_does_not_clear_ownership(self):
        with patch('luda.keyboard.run',side_effect=DesktopError('DISPLAY_UNAVAILABLE','missing')):result=keyboard.recover_keyboard_input()
        self.assertEqual(result['pending_count'],1)
        self.assertEqual(result['recoveries'][0]['reason'],'DISPLAY_UNAVAILABLE')
    def test_live_guardian_is_resumed_and_keeps_gate(self):
        self.guard.poll.return_value=None;self.guard.pid=42
        with patch('luda.keyboard.run',return_value=b'{"session_changed":false}'),patch('luda.keyboard.os.kill') as kill,patch('luda.keyboard._start_watcher') as watcher:
            result=keyboard.recover_keyboard_input()
        self.assertEqual(result['pending_count'],1);kill.assert_called_once();watcher.assert_called_once()
    def test_missing_ownership_metadata_never_guesses(self):
        self.record['plan']=None
        with patch('luda.keyboard.run') as run:result=keyboard.recover_keyboard_input()
        run.assert_not_called();self.assertEqual(result['pending_count'],1)
    def test_replacement_proof_is_explicitly_distinct_from_release(self):
        self.assertTrue(keyboard._completion_proven({'session_changed':True,'cleanup_skipped':True,'cleanup_verified':False}))
        self.assertFalse(keyboard._completion_proven({'session_changed':True,'cleanup_skipped':False}))


if __name__=='__main__':unittest.main()
