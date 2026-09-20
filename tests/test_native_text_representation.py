"""Native EditableText must obey the same opaque-object limits as paste."""
import types
import unittest
from unittest.mock import patch
from test_semantic import load_worker, Text
w=load_worker()

class NativeTextRepresentationTests(unittest.TestCase):
    def setUp(self):
        self.raw=Text();self.raw.path='/field';self.raw.text='A\ufffcZ';self.raw.opaque=True
        self.raw.set_calls=[]
        def replace(text):
            self.raw.set_calls.append(text);self.raw.text=text;return True
        self.raw.set_text_contents=replace
        self.current={'role':'entry','name':'Input','start':'1','states':['editable','enabled','showing'],'interfaces':['Text','EditableText'],'protected':False}
        self.raw.get_interfaces=lambda:['Text','EditableText','Hypertext']
        self.raw.get_hypertext_iface=lambda:self.raw
        self.raw.get_n_links=lambda:1 if self.raw.opaque else 0
        link=types.SimpleNamespace(get_start_index=lambda:self.raw.text.index('\ufffc'),get_end_index=lambda:self.raw.text.index('\ufffc')+1,get_object=lambda _:types.SimpleNamespace(get_role_name=lambda:'paragraph'))
        self.raw.get_link=lambda _:link
        self.binding=patch.object(w,'Atspi',types.SimpleNamespace(Text=Text,Hypertext=types.SimpleNamespace(get_n_links=lambda raw:raw.get_n_links(),get_link=lambda raw,i:raw.get_link(i))))
        self.binding.start();self.addCleanup(self.binding.stop)
    def run_op(self,op,text):
        with patch.object(w,'candidates',return_value=[(self.raw,0)]),patch.object(w,'describe',return_value=self.current):
            return w.dispatch({'op':op,'pid':42,'text':text,'target':{**self.current,'root_path':'/root','root_bus_guid':'a'*32,'path':'/field'}})
    def test_opaque_selected_insert_refused_before_delete(self):
        self.raw.selections=[(0,2)]
        result=self.run_op('insert','X')
        self.assertEqual((result['error'],result['effect']),('TEXT_REPRESENTATION_UNSUPPORTED','none'))
        self.assertEqual(self.raw.edits,[]);self.assertEqual(self.raw.text,'A\ufffcZ')
    def test_opaque_full_replace_refused_without_provider_mutation(self):
        result=self.run_op('set','safe plain replacement')
        self.assertEqual((result['error'],result['effect']),('TEXT_REPRESENTATION_UNSUPPORTED','none'))
        self.assertEqual(self.raw.set_calls,[]);self.assertEqual(self.raw.text,'A\ufffcZ')
    def test_literal_object_character_without_link_stays_supported(self):
        self.raw.opaque=False
        result=self.run_op('insert','x')
        self.assertTrue(result['exact_match']);self.assertEqual(self.raw.text,'Ax\ufffcZ')
    def test_plain_full_replace_remains_exact(self):
        self.raw.text='original';self.raw.opaque=False
        result=self.run_op('set','日本語\n')
        self.assertTrue(result['exact_match']);self.assertEqual(self.raw.text,'日本語\n')
    def test_object_after_selection_delete_stops_before_insert(self):
        self.raw.opaque=False;self.raw.selections=[(0,1)]
        original=self.raw.delete_text
        def delete(start,end):
            accepted=original(start,end);self.raw.opaque=True;return accepted
        self.raw.delete_text=delete
        result=self.run_op('insert','X')
        self.assertEqual((result['error'],result['effect']),('TEXT_REPRESENTATION_UNSUPPORTED','uncertain'))
        self.assertEqual(self.raw.edits,[('delete',0,1)]);self.assertEqual(self.raw.text,'\ufffcZ')
    def test_new_embedded_object_after_insert_is_uncertain(self):
        self.raw.text='AZ';self.raw.opaque=True
        result=self.run_op('insert','\ufffc')
        self.assertEqual((result['error'],result['effect']),('TEXT_REPRESENTATION_UNSUPPORTED','uncertain'))
        self.assertEqual(self.raw.edits,[('insert',1,'\ufffc')])
    def test_new_embedded_object_after_replace_is_uncertain(self):
        self.raw.text='plain';self.raw.opaque=True
        result=self.run_op('set','A\ufffcZ')
        self.assertEqual((result['error'],result['effect']),('TEXT_REPRESENTATION_UNSUPPORTED','uncertain'))
        self.assertEqual(self.raw.set_calls,['A\ufffcZ'])
