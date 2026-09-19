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


class Utf16Text(Text):
    def get_application(self):return types.SimpleNamespace(get_toolkit_name=lambda:'Qt')
    def cp(self,raw):return len(self.text.encode('utf-16-le')[:raw*2].decode('utf-16-le'))
    def get_character_count(self):return len(self.text.encode('utf-16-le'))//2
    def get_text(self,start,end):
        count=self.get_character_count()
        if end > count:return ''  # Qt refuses out-of-range end, unlike GTK.
        return self.text[self.cp(start):None if end==-1 else self.cp(end)]
    def insert_text(self,a,text,length):
        assert length==len(text.encode('utf-16-le'))//2
        return super().insert_text(self.cp(a),text,len(text.encode('utf-8')))
    def delete_text(self,a,b):
        start,end=self.cp(a),self.cp(b)
        accepted=super().delete_text(start,end)
        self.caret=a
        return accepted

class Utf16Semantics(unittest.TestCase):
    def setUp(self):
        self.old=w.Atspi;w.Atspi=types.SimpleNamespace(Text=Utf16Text)
        self.t=Utf16Text();self.current={'protected':False,'interfaces':['Text','EditableText'],'states':['editable','enabled','showing']}
    def tearDown(self):w.Atspi=self.old
    def call(self,op,**kw):return w.semantic(self.t,self.current,{'op':op,**kw})
    def test_insert_astral_into_ascii_normalizes_new_caret(self):
        r=self.call('insert',text='👩🏽\u200d💻');self.assertEqual(self.t.text,'a👩🏽\u200d💻bc');self.assertTrue(r['caret_verified']);self.assertEqual(r['caret_offset'],5)
    def test_select_after_astral_and_replace(self):
        self.t.text='A👩🏽\u200d💻Z'
        r=self.call('select',start_offset=1,end_offset=5);self.assertTrue(r['exact_match']);self.assertEqual(self.t.selections,[(1,8)])
        r=self.call('insert',text='é');self.assertTrue(r['exact_match']);self.assertEqual(self.t.text,'AéZ')
    def test_read_normalizes_count_and_caret(self):
        self.t.text='A😀Z';self.t.caret=3
        t=w.TextAccess(self.t);self.assertTrue(t.utf16);self.assertEqual(t.get_character_count(),3);self.assertEqual(t.get_caret_offset(),2)
    def test_split_surrogate_provider_offset_refused(self):
        self.t.text='A😀Z';self.t.caret=2
        with self.assertRaises(UnicodeDecodeError):w.TextAccess(self.t).get_caret_offset()

class ScopeAndState(unittest.TestCase):
    def setUp(self):
        self.old=w.Atspi;w.Atspi=types.SimpleNamespace(CoordType=types.SimpleNamespace(SCREEN=0))
        self.node=types.SimpleNamespace(path='/root',get_interfaces=lambda:['Component'],get_name=lambda:'Fixture',get_parent=lambda:None)
        self.node.get_component_iface=lambda:types.SimpleNamespace(get_extents=lambda _:types.SimpleNamespace(x=0,y=0,width=100,height=50))
        self.description={'role':'frame','name':'Fixture','start':'1','states':['sensitive','showing'],'bounds':{'x':0,'y':0,'width':100,'height':50}}
        self.req={'op':'inspect','pid':42,'bounds':{'x':10,'y':20,'width':100,'height':50},'frame_bounds':{'x':5,'y':15,'width':110,'height':60}}
    def tearDown(self):w.Atspi=self.old
    def inspect(self,**kw):
        with patch.object(w,'candidates',side_effect=[[(self.node,1)],[(self.node,0)]]),patch.object(w,'describe',return_value=dict(self.description)):
            return w.main({**self.req,**kw})
    def test_fallback_requires_exact_title(self):
        self.assertEqual(self.inspect()['error'],'AMBIGUOUS_ACCESSIBILITY_WINDOW')
        self.assertEqual(self.inspect(window_title='Different')['error'],'AMBIGUOUS_ACCESSIBILITY_WINDOW')
    def test_fallback_removes_unreliable_bounds(self):
        r=self.inspect(window_title='Fixture');self.assertEqual(r['window_mapping'],'unique_title_and_size');self.assertEqual(r['nodes'][0]['bounds_coordinates'],'unavailable');self.assertNotIn('bounds',r['nodes'][0])
    def test_duplicate_fallback_refused(self):
        with patch.object(w,'candidates',return_value=[(self.node,1),(self.node,1)]):
            r=w.main({**self.req,'window_title':'Fixture'})
        self.assertEqual(r['error'],'AMBIGUOUS_ACCESSIBILITY_WINDOW')
    def test_sensitive_showing_is_interactable_but_disabled_is_not(self):
        for states,expected in ((['sensitive','showing'],'verified'),(['showing'],'NOT_INTERACTABLE'),(['sensitive'],'NOT_INTERACTABLE')):
            current={**self.description,'states':states,'protected':False}
            with patch.object(w,'candidates',return_value=[(self.node,0)]),patch.object(w,'describe',return_value=current),patch.object(w,'semantic',return_value={'effect':'verified'}):
                r=w.main({'op':'check','pid':42,'checked':True,'target':{**current,'root_path':'/root','path':'/root'}})
            self.assertEqual(r.get('effect',r.get('error')),expected)

class CaretPostcondition(unittest.TestCase):
    def test_verified_text_survives_unsupported_caret_mutation(self):
        old=w.Atspi;w.Atspi=types.SimpleNamespace(Text=Text)
        try:
            raw=Text()
            current={'protected':False,'interfaces':['Text','EditableText'],'states':['editable','enabled','showing']}
            with patch.object(Text,'set_caret_offset',side_effect=RuntimeError('unsupported')):
                result=w.semantic(raw,current,{'op':'insert','text':'X'})
            self.assertTrue(result['exact_match']);self.assertEqual(raw.text,'aXbc');self.assertFalse(result['caret_verified'])
        finally:w.Atspi=old



class ProtectedInput(unittest.TestCase):
    def setUp(self):
        self.edit=types.SimpleNamespace(set_text_contents=lambda text:True)
        self.node=types.SimpleNamespace(get_editable_text_iface=lambda:self.edit)
        self.current={'protected':True,'interfaces':['EditableText'],'states':['editable'],'role':'password text'}
    def call(self,text='synthetic-secret'):return w.semantic(self.node,self.current,{'op':'secret','text':text})
    def test_acceptance_never_claims_verified_value(self):
        r=self.call();self.assertEqual(r['effect'],'dispatched');self.assertNotIn('synthetic-secret',str(r));self.assertNotIn('exact_match',r)
    def test_provider_exception_cannot_echo_secret(self):
        def broken(text):raise RuntimeError('provider echoed '+text)
        self.edit.set_text_contents=broken
        r=self.call();self.assertEqual(r['effect'],'uncertain');self.assertNotIn('synthetic-secret',str(r));self.assertNotIn('provider echoed',str(r))
    def test_nonprotected_refused(self):
        self.current['protected']=False;self.assertEqual(self.call()['error'],'NOT_PROTECTED_FIELD')
    def test_missing_editable_interface_refused(self):
        self.current['interfaces']=[];self.assertEqual(self.call()['error'],'UNSUPPORTED')
    def test_invalid_secret_never_reaches_provider(self):
        def forbidden(text):raise AssertionError('must not reach provider')
        self.edit.set_text_contents=forbidden
        for text in ('\0','\r','\ud800',None):self.assertEqual(self.call(text)['error'],'UNSUPPORTED_TEXT')

class SelectionProvider:
    def __init__(self):
        self.selected=set();self.ignore_deselect=False
        self.nodes=[types.SimpleNamespace(path='/option/'+str(i),get_index_in_parent=lambda i=i:i) for i in range(3)]
    def get_interfaces(self):return ['Selection']
    def get_role_name(self):return 'list box'
    def get_parent(self):return None
    def get_selection_iface(self):return self
    def get_child_at_index(self,i):return self.nodes[i]
    def is_child_selected(self,i):return i in self.selected
    def get_n_selected_children(self):return len(self.selected)
    def get_selected_child(self,i):return self.nodes[sorted(self.selected)[i]]
    def select_child(self,i):self.selected.add(i);return True
    def deselect_selected_child(self,index):
        return self.deselect_child(sorted(self.selected)[index])
    def deselect_child(self,i):
        if not self.ignore_deselect:self.selected.discard(i)
        return True

class OptionSelection(unittest.TestCase):
    def setUp(self):
        self.old=w.Atspi;w.Atspi=types.SimpleNamespace(Selection=SelectionProvider)
        self.parent=SelectionProvider();self.node=self.parent.nodes[1];self.node.get_parent=lambda:self.parent
        self.current={'protected':False,'role':'list item','states':[]}
        self.states=patch.object(w,'states_of',return_value={'sensitive','showing'});self.states.start()
        self.verifier=patch.object(w,'verify',lambda fn,**_:fn());self.verifier.start()
    def tearDown(self):w.Atspi=self.old;self.states.stop();self.verifier.stop()
    def call(self,**kw):return w.semantic(self.node,self.current,{'op':'choose',**kw})
    def test_single_choice_is_exclusive_without_multiselectable_flag(self):
        self.parent.selected={0,2};r=self.call();self.assertEqual(self.parent.selected,{1});self.assertEqual(r['effect'],'verified')
    def test_extend_preserves_other_choices(self):
        self.parent.selected={0};self.call(extend=True);self.assertEqual(self.parent.selected,{0,1})
    def test_already_selected_is_idempotent(self):
        self.parent.selected={1};r=self.call();self.assertFalse(r['changed'])
    def test_false_deselection_success_not_verified(self):
        self.parent.selected={0};self.parent.ignore_deselect=True;r=self.call();self.assertEqual(r['effect'],'uncertain')
    def test_missing_selection_interface_refused(self):
        self.parent.get_interfaces=lambda:[];self.assertEqual(self.call()['error'],'UNSUPPORTED')
    def test_disabled_parent_refused(self):
        with patch.object(w,'states_of',return_value={'showing'}):self.assertEqual(self.call()['error'],'NOT_INTERACTABLE')
    def test_stale_child_index_refused(self):
        self.node.get_index_in_parent=lambda:0;self.assertEqual(self.call()['error'],'STALE_TARGET')
    def test_invalid_extend_refused(self):self.assertEqual(self.call(extend='yes')['error'],'INVALID_ARGUMENT')

if __name__=='__main__':unittest.main()
