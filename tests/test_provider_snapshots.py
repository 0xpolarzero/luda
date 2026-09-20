"""Fault providers must not turn stale bounded prefixes into exact readback."""
import types
import unittest
from unittest.mock import patch
from test_semantic import load_worker, Text
w=load_worker()

class Snapshots(unittest.TestCase):
    def test_growth_during_bounded_read_is_rejected(self):
        class Growing(Text):
            def get_text(self,start,end):
                self.text+='unexpected suffix'
                return super().get_text(start,end)
        with patch.object(w.Atspi,'Text',Growing,create=True):
            with self.assertRaises(ValueError):w.TextAccess(Growing())
    def test_qt_count_must_match_native_utf16_units(self):
        raw=Text();raw.text='😀';raw.get_application=lambda:types.SimpleNamespace(get_toolkit_name=lambda:'Qt')
        with patch.object(w.Atspi,'Text',Text,create=True):
            with self.assertRaises(ValueError):w.TextAccess(raw)
    def test_public_read_uses_one_coherent_text_snapshot(self):
        class CountReads(Text):
            reads=0
            def get_text(self,start,end):
                self.reads+=1
                return super().get_text(start,end)
        raw=CountReads();raw.path='/field'
        current={'role':'entry','name':'Input','start':'1','states':['editable','enabled','showing'],'interfaces':['Text'],'protected':False}
        with patch.object(w.Atspi,'Text',CountReads,create=True),patch.object(w,'candidates',return_value=[(raw,0)]),patch.object(w,'describe',return_value=current):
            result=w.dispatch({'op':'read','pid':42,'limit':2,'target':{**current,'root_path':'/root','root_bus_guid':'a'*32,'path':'/field'}})
        self.assertEqual(result['text'],'ab');self.assertEqual(result['characters'],3);self.assertTrue(result['truncated'])
        self.assertEqual(raw.reads,1)

    def test_growth_error_reports_whether_mutation_started_without_provider_text(self):
        for mutated in (False,True):
            def change(req):
                req['_mutation_started']=mutated
                raise w.TextChanged('private application text')
            with patch.object(w,'main',side_effect=change):result=w.dispatch({'op':'set'})
            self.assertEqual(result['error'],'TEXT_CHANGED')
            self.assertEqual(result['effect'],'uncertain' if mutated else 'none')
            self.assertNotIn('private application',str(result))
    def test_set_cannot_verify_a_truncated_prefix_after_concurrent_growth(self):
        class GrowingAfterSet(Text):
            mutate=False
            def set_text_contents(self,value):self.text=value;self.mutate=True;return True
            def get_text(self,start,end):
                if self.mutate:self.text+='suffix'
                return super().get_text(start,end)
        raw=GrowingAfterSet();raw.path='/field'
        current={'role':'entry','name':'Input','start':'1','states':['editable','enabled','showing'],'interfaces':['Text','EditableText'],'protected':False}
        with patch.object(w.Atspi,'Text',GrowingAfterSet,create=True),patch.object(w,'candidates',return_value=[(raw,0)]),patch.object(w,'describe',return_value=current):
            result=w.dispatch({'op':'set','pid':42,'text':'new','target':{**current,'root_path':'/root','root_bus_guid':'a'*32,'path':'/field'}})
        self.assertEqual(result['error'],'TEXT_CHANGED');self.assertEqual(result['effect'],'uncertain')
        self.assertEqual(raw.text,'newsuffix')

if __name__=='__main__':unittest.main()
