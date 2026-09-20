"""Mozilla's documented ATK padding is reversible; real U+FEFF is content."""
import types
import unittest
from unittest.mock import patch
from test_semantic import load_worker, Text

w=load_worker()

class GeckoText(unittest.TestCase):
    def test_padding_and_genuine_feff_roundtrip(self):
        for original in ('', 'ASCII', '\ufeffA\ufeff', '😀', '😀\ufeff', '😀\ufeff\ufeffX', '👩🏽\u200d💻 é\n\t'):
            padded=''.join(c+('\ufeff' if ord(c)>65535 else '') for c in original)
            self.assertEqual(w.decode_gecko_text(padded,len(original.encode('utf-16-le'))//2), original)
    def test_inconsistent_convention_refused(self):
        for value,count in [('😀',2),('😀X',2),('😀\ufeff',1),('abc',4)]:
            with self.assertRaises(ValueError):w.decode_gecko_text(value,count)
    def test_offsets_preserve_genuine_feff(self):
        raw=Text();raw.text='A😀\ufeff\ufeffB';raw.caret=4
        raw.get_application=lambda:types.SimpleNamespace(get_toolkit_name=lambda:'Gecko')
        with patch.object(w.Atspi,'Text',Text,create=True):
            t=w.TextAccess(raw)
            self.assertEqual(t.text,'A😀\ufeffB')
            self.assertEqual(t.provider_offset(3),4)
            self.assertEqual(t.public_offset(4),3)
            with self.assertRaises(ValueError):t.public_offset(2)
            t.add_selection(1,2)
            self.assertEqual(raw.selections,[(1,3)])
            self.assertEqual(t.get_selection(0).end_offset,2)
    def test_gecko_ascii_still_has_native_utf16_contract(self):
        raw=Text();raw.get_application=lambda:types.SimpleNamespace(get_toolkit_name=lambda:'Gecko')
        with patch.object(w.Atspi,'Text',Text,create=True):self.assertTrue(w.TextAccess(raw).utf16)
    def test_native_mutations_refused_before_calls(self):
        raw=Text();raw.get_application=lambda:types.SimpleNamespace(get_toolkit_name=lambda:'Gecko')
        for op in ('secret','set','insert'):
            r=w.semantic(raw,{'role':'password text','protected':True}, {'op':op,'text':'do not dispatch'})
            self.assertEqual(r['error'],'UNSUPPORTED');self.assertEqual(raw.edits,[])
    def test_selection_synchronizes_editor_caret_before_range(self):
        raw=Text();raw.caret=0
        raw.get_application=lambda:types.SimpleNamespace(get_toolkit_name=lambda:'Gecko')
        current={'role':'entry','protected':False,'interfaces':['Text'],'states':['editable']}
        with patch.object(w.Atspi,'Text',Text,create=True), patch.object(w,'verify',lambda fn:fn()):
            result=w.semantic(raw,current,{'op':'select','start_offset':1,'end_offset':2})
            self.assertEqual(result['effect'],'verified')
            self.assertEqual(raw.caret,1);self.assertEqual(raw.selections,[(1,2)])
    def test_ignored_caret_prevents_range_dispatch(self):
        class IgnoredCaret(Text):
            def set_caret_offset(self, _):return True
        raw=IgnoredCaret();raw.caret=0
        raw.get_application=lambda:types.SimpleNamespace(get_toolkit_name=lambda:'Gecko')
        current={'role':'entry','protected':False,'interfaces':['Text'],'states':['editable']}
        with patch.object(w.Atspi,'Text',IgnoredCaret,create=True), patch.object(w,'verify',lambda fn:fn()):
            result=w.semantic(raw,current,{'op':'select','start_offset':1,'end_offset':2})
            self.assertEqual(result['error'],'SELECTION_UNVERIFIED');self.assertEqual(result['effect'],'uncertain')
            self.assertEqual(raw.selections,[])
    def test_unrelated_toolkit_feff_not_removed(self):
        raw=Text();raw.text='😀\ufeff'
        with patch.object(w.Atspi,'Text',Text,create=True):self.assertEqual(w.TextAccess(raw).text,raw.text)

if __name__=='__main__':unittest.main()
