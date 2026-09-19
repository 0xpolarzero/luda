"""Deterministic provider fault tests; live_semantic separately proves actual GUI effects."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

# The production worker uses distro PyGObject. These tests replace only its binding
# with a protocol fake, so they also run in the isolated project venv.
def load_worker():
    gi=types.ModuleType('gi');gi.require_version=lambda *_:None
    repo=types.ModuleType('gi.repository');repo.Atspi=types.SimpleNamespace(set_timeout=lambda *_:None)
    spec=importlib.util.spec_from_file_location('semantic_worker',Path(__file__).resolve().parents[1]/'src/luda/ax_worker.py')
    module=importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules,{'gi':gi,'gi.repository':repo}):spec.loader.exec_module(module)
    return module
w=load_worker()
class Text:
    def __init__(self):
        self.text='abc';self.caret=1;self.selections=[];self.edits=[];self.reject_delete=False;self.ignore_delete=False;self.ignore_insert=False
    def get_text(self,start,end):return self.text[start:None if end==-1 else end]
    def get_n_selections(self):return len(self.selections)
    def get_selection(self,index):
        a,b=self.selections[index];return types.SimpleNamespace(start_offset=a,end_offset=b)
    def get_caret_offset(self):return self.caret
    def get_character_count(self):return len(self.text)
    def set_caret_offset(self,n):self.caret=n;return True
    def remove_selection(self,i):self.selections.pop(i);return True
    def set_selection(self,i,a,b):self.selections[i]=(a,b);return True
    def add_selection(self,a,b):self.selections.append((a,b));return True
    def delete_text(self,a,b):
        self.edits.append(('delete',a,b))
        if self.reject_delete:return False
        if not self.ignore_delete:self.text=self.text[:a]+self.text[b:];self.selections=[];self.caret=a
        return True
    def insert_text(self,a,text,length):
        assert length==len(text.encode('utf-8'))
        self.edits.append(('insert',a,text))
        if not self.ignore_insert:self.text=self.text[:a]+text+self.text[a:]
        return True
    def get_text_iface(self):return self
    def get_editable_text_iface(self):return self

class Semantics(unittest.TestCase):
    def setUp(self):
        self.old=w.Atspi;w.Atspi=types.SimpleNamespace(Text=Text)
        self.t=Text();self.current={'protected':False,'interfaces':['Text','EditableText'],'states':['editable','enabled','showing']}
        self.verifier=patch.object(w,'verify',lambda fn,**_:fn());self.verifier.start()
    def tearDown(self):w.Atspi=self.old;self.verifier.stop()
    def call(self,op,**kw):return w.semantic(self.t,self.current,{'op':op,**kw})
    def test_insert_preserves_surroundings(self):
        r=self.call('insert',text='日本\n');self.assertEqual(self.t.text,'a日本\nbc');self.assertTrue(r['exact_match']);self.assertEqual(self.t.caret,4)
    def test_replace_selected_range(self):
        self.t.selections=[(1,2)];self.call('insert',text='X');self.assertEqual(self.t.text,'aXc');self.assertEqual(self.t.selections,[])
    def test_delete_failure_never_inserts(self):
        self.t.selections=[(0,2)];self.t.reject_delete=True
        r=self.call('insert',text='X');self.assertEqual(r['effect'],'uncertain');self.assertEqual(self.t.edits,[('delete',0,2)])
    def test_false_successful_delete_never_inserts(self):
        self.t.selections=[(0,2)];self.t.ignore_delete=True
        r=self.call('insert',text='X');self.assertEqual(r['effect'],'uncertain');self.assertEqual(self.t.edits,[('delete',0,2)])
    def test_false_successful_insert_not_verified(self):
        self.t.ignore_insert=True;r=self.call('insert',text='X');self.assertFalse(r['exact_match']);self.assertEqual(r['effect'],'uncertain')
    def test_protected_operations_no_provider_calls(self):
        self.current['protected']=True
        for op in ('select','insert'):
            self.assertEqual(self.call(op,text='x',start_offset=0,end_offset=0)['error'],'PROTECTED_FIELD')
        self.assertEqual(self.t.edits,[])
    def test_multiple_selection_rejected(self):
        self.t.selections=[(0,1),(2,3)]
        self.assertEqual(self.call('insert',text='x')['error'],'UNSUPPORTED');self.assertEqual(self.t.edits,[])
    def test_invalid_caret_rejected(self):
        self.t.caret=-1;self.assertEqual(self.call('insert',text='x')['error'],'INVALID_SELECTION');self.assertEqual(self.t.edits,[])
    def test_invalid_text_matrix(self):
        for value in (None,13,'\0','\r','\ud800','x'*1_000_001):
            with self.subTest(value_type=type(value).__name__):self.assertEqual(self.call('insert',text=value)['error'],'UNSUPPORTED_TEXT')
        self.assertEqual(self.t.edits,[])
    def test_read_only_refused(self):
        self.current['states']=[];self.assertEqual(self.call('insert',text='x')['error'],'NOT_EDITABLE')
    def test_missing_text_interface_refused(self):
        self.current['interfaces']=[];self.assertEqual(self.call('select',start_offset=0,end_offset=0)['error'],'UNSUPPORTED')
    def test_invalid_selection_matrix(self):
        for a,b in ((True,0),(-1,2),(3,2),(0,4),(0.0,2)):
            with self.subTest(a=a,b=b):self.assertEqual(self.call('select',start_offset=a,end_offset=b)['error'],'INVALID_ARGUMENT')
    def test_empty_insert_collapses_selection(self):
        self.t.selections=[(0,2)];r=self.call('insert',text='');self.assertEqual(self.t.text,'c');self.assertTrue(r['caret_verified'])
    def test_concurrent_text_edit_refused(self):
        original=self.t.get_n_selections;calls=0
        def changed():
            nonlocal calls
            calls+=1
            if calls==2:self.t.text='else'
            return original()
        with patch.object(Text,'get_n_selections',lambda _:changed()):
            # Preserve original bound method above, so no recursion.
            self.assertEqual(self.call('insert',text='x')['error'],'STALE_TARGET')
        self.assertEqual(self.t.edits,[])
    def test_concurrent_caret_change_refused(self):
        original=Text.get_caret_offset;calls=0
        def changed(node):
            nonlocal calls
            calls+=1
            if calls==2:node.caret=2
            return original(node)
        with patch.object(Text,'get_caret_offset',changed):self.assertEqual(self.call('insert',text='x')['error'],'STALE_TARGET')
        self.assertEqual(self.t.edits,[])
    def test_nonfinite_numeric_refused(self):
        for value in (float('nan'),float('inf'),True,'1'):
            self.assertEqual(self.call('value',value=value)['error'],'INVALID_ARGUMENT')

if __name__=='__main__':unittest.main()
