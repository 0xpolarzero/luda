import json,subprocess,sys,unittest
from collections import deque
from contextlib import nullcontext
from types import SimpleNamespace
from unittest.mock import Mock,patch
from luda import server,reporting
from luda_editor_bridge.worker import Worker,Refused
from luda_editor_bridge.browser import OwnedBrowser
from luda.common import DesktopError
from luda_editor_bridge.progress import RichProgress,rich_text_progress,operation_progress
from test_browser_rich import value
import test_browser_rich_clipboard as clipboard_tests

class RichProgressTests(unittest.TestCase):
    def worker(self,states):
        w=Worker('unused');w.protocol=Mock();w.require_text_boundaries=Mock()
        w.snapshot=Mock(side_effect=[({},s) if isinstance(s,dict) else s for s in states])
        return w
    def test_native_first_verified_second_rejected(self):
        before=value('');one=value('PRIVATE');newline=value('PRIVATE\n')
        w=self.worker([before,before,one,one,newline,newline,newline])
        with self.assertRaises(Refused) as caught:w.rich_type('t','PRIVATE\nREJECTED','insert','paragraph',before)
        self.assertEqual(caught.exception.code,'TEXT_MISMATCH')
        self.assertEqual(w.progress.value['verified_completed'],1)
        self.assertEqual(w.progress.value['current_uncertain'],1)
        self.assertEqual(w.progress.value['not_started'],0)
        self.assertNotIn('PRIVATE',json.dumps(w.progress.value))
    def test_preflight_after_verified_first_does_not_start_second(self):
        before=value('');one=value('A');w=self.worker([before,before,one,Refused('FOCUS_CHANGED')])
        with self.assertRaises(Refused):w.rich_type('t','A\nB','insert','paragraph',before)
        self.assertEqual((w.progress.value['verified_completed'],w.progress.value['current_uncertain'],w.progress.value['not_started']),(1,0,1))
        self.assertEqual(w.protocol.send.call_count,1)
    def test_native_intermediate_keyup_failure_is_not_verified(self):
        before=value('');one=value('A');w=self.worker([before,before,one,one])
        w.protocol.send.side_effect=[None,None,RuntimeError('PRIVATE')]
        with self.assertRaises(RuntimeError):w.rich_type('t','A\nB','insert','paragraph',before)
        self.assertEqual((w.progress.value['verified_completed'],w.progress.value['current_uncertain']),(1,1))
    def test_clipboard_after_first_verified_preflight_failure(self):
        before=value('');one=value('A')
        w=clipboard_tests.RichClipboardTests().worker([before,before,before,before,one,one])
        w.clipboard.preflight.side_effect=[None,None,DesktopError('INPUT_HELD','private')]
        with self.assertRaises(Refused):w.rich_clipboard_type('t','A\nB','insert','paragraph',before)
        self.assertEqual((w.progress.value['verified_completed'],w.progress.value['current_uncertain'],w.progress.value['not_started']),(1,0,1))
        self.assertEqual(w.clipboard.stage.call_count,1)
    def test_clipboard_publication_without_paste_is_conservatively_uncertain(self):
        before=value('');w=clipboard_tests.RichClipboardTests().worker([before,before,Refused('FOCUS_CHANGED')])
        with self.assertRaises(Refused):w.rich_clipboard_type('t','A\nB','insert','paragraph',before)
        self.assertEqual((w.progress.value['verified_completed'],w.progress.value['current_uncertain'],w.progress.value['not_started']),(0,1,1))
        w.protocol.send.assert_not_called();self.assertTrue(w.clipboard_changed)
    def test_strict_projection_rejects_payload_and_wrong_counts(self):
        p=RichProgress(2);p.complete();p.begin();good=p.value
        self.assertEqual(rich_text_progress(good,2),good)
        for bad in ({**good,'text':'PRIVATE'},{**good,'requested':True},{**good,'not_started':1},{**good,'application_commit_verified':True},{**good,'unit':'key_chord'}):
            self.assertIsNone(rich_text_progress(bad))
        self.assertIsNone(rich_text_progress(good,3))
    def test_public_error_history_and_report_keep_only_progress(self):
        p=RichProgress(2);p.complete();p.begin();progress=p.value
        backend=SimpleNamespace(control=SimpleNamespace(require_active=lambda:None),transaction=nullcontext,require_supported_backend=lambda:None,
            type_text=Mock(side_effect=DesktopError('TEXT_MISMATCH','Mismatch.',effect='uncertain',details={'progress':progress})))
        history=deque()
        with patch.object(server,'get_backend',return_value=backend),patch.object(server,'require_session_input'),patch.object(server,'_history',history):
            response=server.execute('type_text','observed','PRIVATE\nPAYLOAD',_progress_parser=operation_progress)
        self.assertEqual(json.loads(response.content[0].text)['details']['progress'],progress)
        self.assertEqual(history[-1]['progress'],progress)
        self.assertEqual(reporting.project_history(history,progress_parser=operation_progress)[-1]['progress'],progress)
        self.assertNotIn('PRIVATE',response.content[0].text+json.dumps(list(history)))
        self.assertNotIn('progress',reporting.project_history([dict(history[-1],progress={**progress,'text':'PRIVATE'})])[-1])
    def test_actual_receipt_transport_filters_untrusted_progress(self):
        p=RichProgress(2);p.complete();p.begin();good=p.value
        for progress in (good,{**good,'text':'PRIVATE'},{**good,'requested':3},{'unit':'key_chord'}):
            receipt={'error':'TEXT_MISMATCH','effect':'uncertain','progress':progress}
            code='import sys,json;sys.stdin.readline();print('+repr(json.dumps(receipt))+',flush=True);sys.stdin.read()'
            process=subprocess.Popen([sys.executable,'-c',code],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
            owner=OwnedBrowser(None);owner.process=process
            try:
                with self.assertRaises(DesktopError) as caught:owner.request('type',token='t',text='PRIVATE\nPAYLOAD',mode='insert')
                if progress==good:self.assertEqual(caught.exception.details['progress'],good)
                else:self.assertNotIn('progress',caught.exception.details)
                self.assertNotIn('PRIVATE',json.dumps(caught.exception.details))
            finally:
                process.stdin.close();process.wait(timeout=2);process.stdout.close()

    def test_lost_receipt_never_synthesizes_progress(self):
        process=subprocess.Popen([sys.executable,'-c','import sys;sys.stdin.readline()'],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
        owner=OwnedBrowser(None);owner.process=process;owner.close=Mock()
        try:
            with self.assertRaises(DesktopError) as caught:owner.request('type',token='t',text='FIRST\nSECOND',mode='insert')
            self.assertNotIn('progress',caught.exception.details)
            self.assertEqual(caught.exception.effect,'uncertain')
        finally:
            process.stdin.close();process.wait(timeout=2);process.stdout.close()

    def test_malformed_progress_is_removed_from_public_error(self):
        p=RichProgress(2)
        backend=SimpleNamespace(control=SimpleNamespace(require_active=lambda:None),transaction=nullcontext,require_supported_backend=lambda:None,
            type_text=Mock(side_effect=DesktopError('TEXT_MISMATCH','Mismatch.',effect='uncertain',details={'progress':{**p.value,'text':'PRIVATE'}})))
        with patch.object(server,'get_backend',return_value=backend),patch.object(server,'require_session_input'):
            response=server.execute('type_text','observed','input')
        self.assertNotIn('PRIVATE',response.content[0].text)
        self.assertNotIn('progress',json.loads(response.content[0].text).get('details',{}))

    def test_invalid_next_packet_cannot_reuse_previous_progress(self):
        import io
        from luda import _browser_worker as module
        worker=Mock();worker.context=None;worker.pw=None;worker.effect='none';worker.clipboard_changed=False
        def dispatch(request):
            worker.progress=RichProgress(1);worker.progress.complete()
            return {'effect':'verified'}
        worker.dispatch.side_effect=dispatch
        worker.receipt_progress.side_effect=lambda:rich_text_progress(worker.progress.value) if worker.progress is not None else None
        output=io.StringIO()
        with patch.object(module,'Worker',return_value=worker),patch.object(module.sys,'argv',['worker','unused']),patch.object(module.sys,'stdin',SimpleNamespace(buffer=io.BytesIO(b'{}\ninvalid\n'))),patch.object(module.sys,'stdout',output):
            module.main(lambda profile:worker)
        replies=[json.loads(row) for row in output.getvalue().splitlines()]
        self.assertEqual(replies[0]['progress']['verified_completed'],1)
        self.assertNotIn('progress',replies[1])
