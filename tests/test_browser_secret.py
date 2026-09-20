import json,os,subprocess,sys,tempfile,time,unittest
from unittest.mock import Mock
from luda._browser_worker import Worker,Refused
from luda._browser_secret import replace as _replace
def replace(worker,token,text):return _replace(worker,token,text,Refused)
from luda.browser import OwnedBrowser
from luda.common import DesktopError

class BrowserSecretTests(unittest.TestCase):
 def worker(self):
  w=Worker.__new__(Worker);w.effect='none';w.protocol=Mock();w.clipboard=Mock();w.native_target={'xid':42,'generation':'owned'};w.page=Mock()
  node=Mock();node.evaluate.return_value={'selected':True};w.snapshot=Mock(return_value=({'node':node},{'focused':True,'selection_all':True}))
  return w
 def test_dispatch_only_without_clipboard_or_content_readback(self):
  w=self.worker();result=replace(w,'token','synthetic-secret')
  self.assertEqual(result,{'effect':'dispatched','secret_dispatched':True})
  w.clipboard.stage.assert_not_called();w.clipboard.verify.assert_not_called()
  self.assertEqual([c.args[0] for c in w.protocol.send.call_args_list],['Input.insertText'])
 def test_unknown_active_or_stale_before_focus_never_inputs(self):
  for code in ('COMPOSITION_UNKNOWN','IME_COMPOSITION_ACTIVE','STALE_TARGET','NOT_PROTECTED_FIELD'):
   w=self.worker();w.snapshot.side_effect=Refused(code)
   with self.assertRaises(Refused):replace(w,'token','synthetic-secret')
   w.protocol.send.assert_not_called();w.page.bring_to_front.assert_not_called();self.assertEqual(w.effect,'none')
 def test_post_native_plan_guard_precedes_selection_and_content(self):
  w=self.worker();w.snapshot.side_effect=[({'node':Mock()},{'focused':True}),Refused('FOCUS_CHANGED')]
  with self.assertRaises(Refused):replace(w,'token','synthetic-secret')
  w.protocol.send.assert_not_called();self.assertEqual(w.effect,'none')
 def test_replacement_after_select_prevents_content_dispatch(self):
  w=self.worker();node=Mock();node.evaluate.return_value={'selected':True};v=({'node':node},{'focused':True,'selection_all':True})
  w.snapshot.side_effect=[v,v,Refused('STALE_TARGET')]
  with self.assertRaises(Refused):replace(w,'token','synthetic-secret')
  self.assertEqual(w.effect,'uncertain');self.assertNotIn('Input.insertText',[c.args[0] for c in w.protocol.send.call_args_list])
 def test_masking_change_after_input_is_uncertain_no_retry(self):
  w=self.worker();node=Mock();node.evaluate.return_value={'selected':True};v=({'node':node},{'focused':True,'selection_all':True});w.snapshot.side_effect=[v,v,v,Refused('NOT_PROTECTED_FIELD')]
  with self.assertRaises(Refused):replace(w,'token','synthetic-secret')
  self.assertEqual(w.effect,'uncertain');self.assertEqual(sum(c.args[0]=='Input.insertText' for c in w.protocol.send.call_args_list),1)
 def test_empty_replace_uses_backspace_without_enter_or_plaintext(self):
  w=self.worker();replace(w,'token','')
  self.assertEqual([c.args[1]['key'] for c in w.protocol.send.call_args_list],['Backspace','Backspace'])
 def test_invalid_single_line_text_has_no_effect(self):
  for text in ('a\nb','\0','\r','\ud800','x'*64001):
   w=self.worker()
   with self.assertRaises(Refused):replace(w,'token',text)
   w.snapshot.assert_not_called()
 def test_parent_rejects_secret_payload_in_success(self,field="text"):
  marker='SYNTHETIC_SECRET_MUST_NOT_ECHO'
  with tempfile.TemporaryDirectory() as directory:
   script='import sys,json\njson.loads(sys.stdin.readline())\nprint(json.dumps('+repr({'effect':'dispatched','secret_dispatched':True,field:marker})+'),flush=True)\nsys.stdin.read()'
   p=subprocess.Popen([sys.executable,'-c',script],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
   owner=OwnedBrowser(None);owner.process=p;owner.close=Mock()
   os.set_blocking(p.stdin.fileno(),False);os.set_blocking(p.stdout.fileno(),False)
   try:
    with self.assertRaises(DesktopError) as caught:owner.request('secret',token='t',text=marker)
    self.assertEqual(caught.exception.code,'BROWSER_PROTOCOL_ERROR');self.assertNotIn(marker,str(caught.exception));self.assertEqual(caught.exception.effect,'uncertain')
   finally:p.kill();p.wait();p.stdin.close();p.stdout.close()

 def test_utf16_maxlength_refuses_astral_before_focus(self):
  w=self.worker();w.snapshot.return_value=({'node':Mock()},{'focused':False,'max_length':1})
  with self.assertRaises(Refused):replace(w,'token','😀')
  self.assertEqual(w.effect,'none');w.page.bring_to_front.assert_not_called();w.protocol.send.assert_not_called()

 def test_parent_rejects_progress_before_any_secret_projection(self):
  self.test_parent_rejects_secret_payload_in_success(field='progress')
