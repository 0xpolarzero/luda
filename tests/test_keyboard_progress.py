"""Partial dispatch evidence must remain ordered, bounded and payload-free."""
from collections import deque
from contextlib import nullcontext
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from luda._keyboard_guard import KeyDispatchProgress
from luda.keyboard import key_dispatch_progress
from luda.common import DesktopError
from luda import server, reporting


class KeyProgress(unittest.TestCase):
    def test_completed_partial_and_not_started_partition(self):
        p=KeyDispatchProgress(3)
        p.start(1);p.complete(1)
        between=p.snapshot()
        self.assertEqual((between['dispatched'],between['possibly_partial'],between['not_started']),(1,0,2))
        p.start(2)
        partial=p.snapshot()
        self.assertEqual((partial['dispatched'],partial['possibly_partial'],partial['not_started']),(1,1,1))
        self.assertFalse(partial['application_outcome_verified'])
        p.complete(2);p.start(3);p.complete(3)
        self.assertEqual(p.snapshot()['dispatched'],3)
        self.assertEqual(between['dispatched'],1)

    def test_out_of_order_duplicate_and_unbounded_acknowledgments_refused(self):
        for count in (0,21,True,None,'3'):
            with self.subTest(count=count),self.assertRaises(ValueError):KeyDispatchProgress(count)
        p=KeyDispatchProgress(2)
        for action,number in ((p.complete,1),(p.start,2),(p.start,True)):
            with self.assertRaises(ValueError):action(number)
        p.start(1)
        for action,number in ((p.start,1),(p.start,2),(p.complete,2)):
            with self.assertRaises(ValueError):action(number)
        p.complete(1)
        with self.assertRaises(ValueError):p.complete(1)

    def test_untrusted_progress_never_retains_payload_or_wrong_totals(self):
        good=KeyDispatchProgress(3).snapshot()
        self.assertEqual(key_dispatch_progress(good,3),good)
        self.assertIsNone(key_dispatch_progress(good,2))
        for bad in ({**good,'text':'PRIVATE'},{**good,'unit':'PRIVATE'},
                    {**good,'dispatched':True},{**good,'requested':999},
                    {**good,'possibly_partial':2},{**good,'not_started':2},
                    {**good,'application_outcome_verified':True},None,[]):
            with self.subTest(value=bad):self.assertIsNone(key_dispatch_progress(bad))

    def test_public_error_and_status_retain_counts_not_application_success(self):
        progress=KeyDispatchProgress(4);progress.start(1);progress.complete(1);progress.start(2)
        value=progress.snapshot()
        backend=SimpleNamespace(control=SimpleNamespace(require_active=lambda:None),
            transaction=nullcontext,require_supported_backend=lambda:None,
            key=Mock(side_effect=DesktopError('CANCELLED','Inspect before retrying.',effect='uncertain',details={'progress':value})))
        history=deque()
        with patch.object(server,'get_backend',return_value=backend),patch.object(server,'require_session_input'),patch.object(server,'_history',history):
            response=server.execute('key','observed','Down',4)
        payload=json.loads(response.content[0].text)
        self.assertTrue(response.isError);self.assertEqual(payload['effect'],'uncertain')
        self.assertEqual(payload['details']['progress'],value)
        self.assertEqual(history[-1]['progress'],value)
        self.assertEqual(reporting.project_history(history)[-1]['progress'],value)
        self.assertNotIn('progress',reporting.project_history([dict(history[-1],progress={**value,'text':'PRIVATE'})])[-1])

    def test_native_second_preflight_failure_records_only_first_dispatch(self):
        from luda import _keyboard_native as native
        import io
        request={'chord':'Down','target':99,'target_generation':'a'*32,'count':3,
                 'keycodes':[116],'server_generation':'owned','group':0,'locked_mods':0}
        keyboard=Mock()
        keyboard.plan.side_effect=[request,{**request,'group':1}]
        keyboard.state.return_value=SimpleNamespace(group=0,locked_mods=0)
        keyboard.client_resource.return_value={'xid':123,'generation':'b'*32}
        messages=[]
        with patch.object(native,'Keyboard',return_value=keyboard),patch.object(native,'generation',return_value='owned'),patch.object(native.sys,'argv',['helper','inject']),patch.object(native.sys,'stdin',SimpleNamespace(buffer=io.BytesIO(json.dumps(request).encode()+b'\n'))),patch.object(native,'emit',side_effect=messages.append),patch.object(native.time,'sleep'):
            native.main()
        self.assertEqual([m for m in messages if 'dispatch_started' in m],[{'dispatch_started':1}])
        self.assertEqual([m for m in messages if 'dispatch_completed' in m],[{'dispatch_completed':1}])
        self.assertEqual(messages[-1]['code'],'KEYMAP_CHANGED')
        keyboard.press_target.assert_called_once_with(116,99,'a'*32)
        keyboard.event.assert_called_once_with(116,False)

    def test_actual_companion_error_receipt_reaches_public_dispatch_details(self):
        import subprocess,sys
        from luda import keyboard
        original=subprocess.Popen
        progress=KeyDispatchProgress(3);progress.start(1);progress.complete(1);progress.start(2)
        valid=progress.snapshot()
        for value in (valid,{**valid,'text':'PRIVATE'},{**valid,'requested':4}):
            result={'armed':True,'code':'CANCELLED','message':'Interrupted.',
                    'effect':'uncertain','cleanup_verified':True,'progress':value}
            script='import sys,json;sys.stdin.readline();print('+repr(json.dumps(result))+',flush=True)'
            def spawn(command,**kwargs):return original([sys.executable,'-c',script],**kwargs)
            with patch.object(keyboard.subprocess,'Popen',side_effect=spawn),self.assertRaises(DesktopError) as caught:
                keyboard._dispatch_plan({'count':3})
            self.assertEqual(caught.exception.code,'CANCELLED')
            self.assertTrue(caught.exception.details['cleanup_verified'])
            if value==valid:self.assertEqual(caught.exception.details['progress'],valid)
            else:self.assertNotIn('progress',caught.exception.details)
