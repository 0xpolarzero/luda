import unittest
from unittest.mock import Mock
from luda._browser_rich import decode, RichInvalid, unchanged_prefix
from luda._browser_worker import Worker,Refused


def model(text,marks=None):
    return {'type':'doc','content':[{'type':'paragraph',**({'content':[{'type':'text','text':part,**({'marks':marks} if marks else {})}]} if part else {})} for part in text.split('\n')]}


def value(text,marks=None):
    native=len(text.encode('utf-16-le'))//2+len(text.split('\n'))
    return decode({'model':model(text,marks),'selection':{'type':'text','anchor':native,'head':native},'stored_marks':None,'focused':True})


class BrowserRichTests(unittest.TestCase):
    def test_unicode_paragraph_mapping_retains_empty_trailing_blocks(self):
        result=value('A😀\n\n')
        self.assertEqual(result['text'],'A😀\n\n');self.assertEqual(result['paragraphs'],['A😀','',''])
        self.assertEqual((result['start'],result['end']),(4,4))

    def test_prefix_marks_compare_independently_of_text_run_merging(self):
        original=value('strong',[{'type':'strong'}]);after=value('strong plus',[{'type':'strong'}])
        self.assertTrue(unchanged_prefix(original,after));self.assertFalse(unchanged_prefix(original,value('strong plus')))

    def test_unsupported_structure_and_marks_are_not_flattened(self):
        for node in ({'type':'hard_break'},{'type':'image','attrs':{'src':'x'}},{'type':'text','text':'x','marks':[{'type':'link','attrs':{'href':'x'}}]}):
            with self.subTest(node=node),self.assertRaises(RichInvalid):decode({'model':{'type':'doc','content':[{'type':'paragraph','content':[node]}]}})

    def test_mid_surrogate_selection_is_unavailable_not_guessed(self):
        result=decode({'model':model('😀'),'selection':{'type':'text','anchor':2,'head':2}})
        self.assertIsNone(result['start']);self.assertIsNone(result['end'])

    def test_missing_paragraph_policy_precedes_focus_and_input(self):
        w=Worker('unused');w.focus=Mock();w.protocol=Mock();before=value('');before['focused']=False
        with self.assertRaises(Refused) as caught:w.rich_type('t','a\nb','replace',None,before)
        self.assertEqual(caught.exception.code,'LINE_BREAK_SEMANTICS_REQUIRED');w.focus.assert_not_called();w.protocol.send.assert_not_called()

    def test_middle_insertion_and_action_budget_refuse_before_focus(self):
        for text,before in [('x',value('abc')),('\n'*27,value(''))]:
            if text=='x':before['start']=before['end']=1
            w=Worker('unused');w.focus=Mock();w.protocol=Mock()
            with self.assertRaises(Refused):w.rich_type('t',text,'insert','paragraph',before)
            w.focus.assert_not_called();w.protocol.send.assert_not_called()

    def test_detected_focus_change_after_dispatch_never_replays(self):
        w=Worker('unused');w.protocol=Mock();before=value('');w.snapshot=Mock(side_effect=[({},before),({},before),Refused('FOCUS_CHANGED')])
        with self.assertRaises(Refused):w.rich_type('t','once','insert',None,before)
        self.assertEqual(w.protocol.send.call_count,1);self.assertEqual(w.effect,'uncertain')

    def test_same_length_document_change_during_select_stops_before_replacement(self):
        before=value('old');changed=value('NEW');selected=value('NEW');selected.update(start=0,end=3,selection={'type':'all'})
        w=Worker('unused');w.protocol=Mock();w.snapshot=Mock(side_effect=[({},before),({},changed),({},selected),({},selected)])
        with self.assertRaises(Refused) as caught:w.rich_type('t','target','replace',None,before)
        self.assertEqual(caught.exception.code,'TEXT_CHANGED');self.assertEqual(w.effect,'uncertain')
        self.assertEqual([c.args[0] for c in w.protocol.send.call_args_list],['Input.dispatchKeyEvent','Input.dispatchKeyEvent'])

    def test_unsupported_pending_marks_refuse_before_a_new_document_can_be_created(self):
        with self.assertRaises(RichInvalid) as caught:
            decode({'model':model(''),'stored_marks':[{'type':'link','attrs':{'href':'https://example.invalid'}}]})
        self.assertEqual(caught.exception.code,'TEXT_REPRESENTATION_UNSUPPORTED')

    def test_reviewed_fixture_bundle_and_shipped_bridge_match_identity(self):
        from pathlib import Path
        import hashlib,json
        root=Path(__file__).resolve().parents[1];fixture=root/'tests/fixtures/owned-rich-editor'
        identity=json.loads((fixture/'bundle-identity.json').read_text())
        for name,digest in identity['files'].items():self.assertEqual(hashlib.sha256((fixture/name).read_bytes()).hexdigest(),digest,name)
        self.assertEqual(hashlib.sha256((root/'integrations/prosemirror/luda-prosemirror.mjs').read_bytes()).hexdigest(),identity['bridge_sha256'])

    def test_known_final_paragraph_overflow_refuses_before_focus_or_keys(self):
        before=value('\n'*127);before['focused']=False
        w=Worker('unused');w.focus=Mock();w.protocol=Mock()
        with self.assertRaises(Refused) as caught:w.rich_type('t','\n','insert','paragraph',before)
        self.assertEqual(caught.exception.code,'VERIFICATION_LIMIT');self.assertEqual(w.effect,'none')
        w.focus.assert_not_called();w.protocol.send.assert_not_called()
