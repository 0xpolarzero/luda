"""Older Chromium advertises Document but cannot return selection ranges."""
import unittest
from unittest.mock import patch
import test_semantic as semantic
w=semantic.w

class OlderChromiumSelection(unittest.TestCase):
    def setUp(self):semantic.ChromiumSelections.setUp(self)
    def tearDown(self):semantic.ChromiumSelections.tearDown(self)
    def test_empty_document_nonbmp_never_trusts_corrupted_legacy_range(self):
        self.ranges.clear()
        with self.assertRaises(w.SelectionUnavailable):w.TextAccess(self.raw).get_selection(0)
    def test_empty_document_bmp_legacy_range_is_exact(self):
        self.ranges.clear();self.raw.text='日本語\té\n';self.raw.selections=[(1,6)]
        text=w.TextAccess(self.raw);selection=text.get_selection(0)
        self.assertEqual((selection.start_offset,selection.end_offset),(1,6))
        self.assertEqual(text.selection_source,'Text')
    def test_nonempty_foreign_document_range_does_not_fall_back(self):
        self.raw.text='abcdef';self.ranges[0].end_object=type('Other',(),{'path':'/foreign'})()
        with self.assertRaises(w.SelectionUnavailable):w.TextAccess(self.raw).get_selection(0)
    def test_diagnostic_distinguishes_read_from_partially_changed_selection(self):
        def failed(request):
            if request['op']=='select':request['_mutation_started']=True
            raise w.SelectionUnavailable('native provider text must never escape')
        with patch.object(w,'main',side_effect=failed):
            for op,effect in (('read','none'),('select','uncertain')):
                result=w.dispatch({'op':op})
                self.assertEqual(result['error'],'SELECTION_UNVERIFIABLE')
                self.assertEqual(result['effect'],effect)
                self.assertNotIn('native provider text',str(result))

if __name__=='__main__':unittest.main()
