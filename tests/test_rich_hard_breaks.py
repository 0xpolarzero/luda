import unittest
from unittest.mock import Mock
from luda._browser_rich import decode,RichInvalid,unchanged_prefix
from luda._browser_worker import Worker,Refused

CONTRACT='basic-paragraphs-hard-breaks-v1'
def value(parts,caret=None):
 paragraphs=[];size=0
 for paragraph in parts:
  nodes=[]
  for item in paragraph:
   if item is None:nodes.append({'type':'hard_break'});size+=1
   else:nodes.append({'type':'text','text':item});size+=len(item.encode('utf-16-le'))//2
  paragraphs.append({'type':'paragraph',**({'content':nodes} if nodes else {})});size+=2
 pos=size-1 if caret is None else caret
 return decode({'contract':CONTRACT,'model':{'type':'doc','content':paragraphs},'selection':{'type':'text','anchor':pos,'head':pos},'stored_marks':None,'focused':True})

class HardBreaks(unittest.TestCase):
 def test_breaks_and_paragraphs_have_distinct_layout_and_native_offsets(self):
  v=value([['A😀',None],['é',None,None]],caret=5)
  self.assertEqual(v['text'],'A😀\n\né\n\n');self.assertEqual(v['layout'],'tthptthh');self.assertEqual(v['start'],3)
  v=value([['A😀',None],['é']],caret=7);self.assertEqual(v['start'],4)
 def test_same_plaintext_different_structure_is_not_preserved(self):
  hard=value([['A',None,'B']]);paragraph=value([['A'],['B']]);self.assertEqual(hard['text'],paragraph['text']);self.assertFalse(unchanged_prefix(hard,paragraph))
 def test_legacy_and_unsupported_mixed_nodes_refuse(self):
  v=value([['A',None]])
  with self.assertRaises(RichInvalid):decode({**v,'contract':'basic-paragraphs-v1'})
  for node in [{'type':'hard_break','attrs':{'custom':1}},{'type':'image'},{'type':'hard_break','marks':[{'type':'link'}]}]:
   v['model']['content'][0]['content'].append(node)
   with self.assertRaises(RichInvalid):decode(v)
   v['model']['content'][0]['content'].pop()
 def test_hard_break_requires_declared_capability_before_focus(self):
  from test_browser_rich import value as legacy
  w=Worker('unused');w.focus=Mock();w.protocol=Mock()
  for transport in [w.rich_type,w.rich_clipboard_type]:
   with self.assertRaises(Refused) as caught:transport('t','A\nB','replace','hard_break',legacy(''))
   self.assertEqual(caught.exception.code,'UNSUPPORTED_ACTION')
  w.focus.assert_not_called();w.protocol.send.assert_not_called()
 def test_native_shift_enter_exact_hard_break_and_caret(self):
  before=value([['A']]);after=value([['A',None]])
  w=Worker('unused');w.protocol=Mock();w.rich_key=Mock();w.require_text_boundaries=Mock();w.snapshot=Mock(side_effect=[({},before),({},before),({},after)])
  result=w.rich_type('t','\n','insert','hard_break',before)
  self.assertTrue(result['exact_match']);self.assertEqual(result['model'],after['model']);w.rich_key.assert_called_once_with('Enter','Enter',13,8)
 def test_wrong_key_binding_same_lf_never_verifies_or_retries(self):
  before=value([['A']]);wrong=value([['A'],[]])
  w=Worker('unused');w.protocol=Mock();w.rich_key=Mock();w.require_text_boundaries=Mock();w.snapshot=Mock(side_effect=[({},before),({},before),({},wrong)])
  with self.assertRaises(Refused) as caught:w.rich_type('t','\nB','insert','hard_break',before)
  self.assertEqual(caught.exception.code,'TEXT_MISMATCH');self.assertEqual(w.rich_key.call_count,1);w.protocol.send.assert_not_called()
 def test_hard_break_does_not_consume_paragraph_budget(self):
  before=value([[]]*127+[['A']]);after=value([[]]*127+[['A',None]])
  w=Worker('unused');w.protocol=Mock();w.rich_key=Mock();w.require_text_boundaries=Mock();w.snapshot=Mock(side_effect=[({},before),({},before),({},after)])
  self.assertTrue(w.rich_type('t','\n','insert','hard_break',before)['exact_match'])

 def test_known_structural_node_overflow_refuses_before_focus_and_clipboard(self):
  before=value([[None]*4095]);w=Worker('unused');w.focus=Mock();w.clipboard=Mock();w.protocol=Mock()
  for transport in [w.rich_type,w.rich_clipboard_type]:
   with self.assertRaises(Refused) as caught:transport('t','\n','insert','hard_break',before)
   self.assertEqual(caught.exception.code,'VERIFICATION_LIMIT')
  w.focus.assert_not_called();w.clipboard.preflight.assert_not_called();w.protocol.send.assert_not_called()

 def test_separated_text_runs_count_toward_known_node_budget(self):
  before=value([['X',None]*2047+['X']]);w=Worker('unused');w.focus=Mock();w.clipboard=Mock();w.protocol=Mock()
  for transport in [w.rich_type,w.rich_clipboard_type]:
   with self.assertRaises(Refused) as caught:transport('t','\nX','insert','hard_break',before)
   self.assertEqual(caught.exception.code,'VERIFICATION_LIMIT')
  w.focus.assert_not_called();w.clipboard.preflight.assert_not_called();w.protocol.send.assert_not_called()

 def test_read_boundary_metadata_is_prefix_bounded_without_hidden_model(self):
  current=value([['A',None,'B'],['C']]);current['composition']={'known':True,'active':False}
  w=Worker('unused');w.snapshot=Mock(return_value=({},current));result=w.read('t',2)
  self.assertEqual(result['text'],'A\n');self.assertIsNone(result['model']);self.assertTrue(result['model_truncated']);self.assertEqual(result['line_break_boundaries'],[{'offset':1,'kind':'hard_break'}])
 def test_offline_fixture_sources_and_bridge_match_recorded_hashes(self):
  from pathlib import Path
  import hashlib,json
  root=Path(__file__).resolve().parents[1];fixture=root/'tests/fixtures/owned-rich-hard-breaks';identity=json.loads((fixture/'bundle-identity.json').read_text())
  for name,digest in identity['files'].items():self.assertEqual(hashlib.sha256((fixture/name).read_bytes()).hexdigest(),digest,name)
  self.assertEqual(hashlib.sha256((root/'integrations/prosemirror/luda-prosemirror.mjs').read_bytes()).hexdigest(),identity['bridge_sha256'])
