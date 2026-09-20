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
    module._native_bus_generation=module.bus_generation
    module.bus_generation=lambda:'a'*32
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
        self.node=types.SimpleNamespace(app=types.SimpleNamespace(bus_name=':1.42'),path='/root',get_interfaces=lambda:['Component'],get_name=lambda:'Fixture',get_parent=lambda:None)
        self.node.get_component_iface=lambda:types.SimpleNamespace(get_extents=lambda _:types.SimpleNamespace(x=0,y=0,width=100,height=50))
        self.description={'role':'frame','name':'Fixture','start':'1','states':['sensitive','showing'],'bounds':{'x':0,'y':0,'width':100,'height':50}}
        self.req={'op':'inspect','pid':42,'bounds':{'x':10,'y':20,'width':100,'height':50},'frame_bounds':{'x':5,'y':15,'width':110,'height':60}}
    def tearDown(self):w.Atspi=self.old
    def inspect(self,**kw):
        with patch.object(w,'candidates',side_effect=[[(self.node,1)],[(self.node,0)]]),patch.object(w,'describe',return_value=dict(self.description)):
            return w.main({**self.req,**kw})
    def test_fallback_requires_exact_title(self):
        self.assertEqual(self.inspect()['error'],'ACCESSIBILITY_UNAVAILABLE')
        self.assertEqual(self.inspect(window_title='Different')['error'],'ACCESSIBILITY_UNAVAILABLE')
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
                r=w.main({'op':'check','pid':42,'checked':True,'target':{**current,'root_path':'/root','root_bus_guid':'a'*32,'path':'/root'}})
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
        self.selected=set();self.ignore_deselect=False;self.path="/list";self.app=types.SimpleNamespace(bus_name=":1.42")
        self.nodes=[types.SimpleNamespace(path='/option/'+str(i),get_index_in_parent=lambda i=i:i,app=self.app,get_role_name=lambda:'list item',get_name=lambda i=i:'Option '+str(i)) for i in range(3)]
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
        self.current={'protected':False,'role':'list item','states':[],'name':self.node.get_name(),'name_fingerprint':w.bounded_name_identity(self.node,False)[1]}
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



class ChromiumSelections(unittest.TestCase):
    def setUp(self):
        self.old=w.Atspi
        self.raw=Text();self.raw.text='A👩🏽\u200d💻Z';self.raw.path='/field';self.raw.selections=[(1,3)]
        self.raw.get_application=lambda:types.SimpleNamespace(get_toolkit_name=lambda:'Chromium')
        self.document=types.SimpleNamespace(get_interfaces=lambda:['Document'])
        self.document.get_document_iface=lambda:self.document
        self.raw.get_parent=lambda:self.document
        self.ranges=[types.SimpleNamespace(start_object=self.raw,end_object=self.raw,start_offset=1,end_offset=5)]
        w.Atspi=types.SimpleNamespace(Text=Text,Document=types.SimpleNamespace(get_text_selections=lambda _:self.ranges))
    def tearDown(self):w.Atspi=self.old
    def test_document_range_replaces_double_converted_text_range(self):
        t=w.TextAccess(self.raw);r=t.get_selection(0);self.assertEqual((r.start_offset,r.end_offset),(1,5));self.assertEqual(t.selection_source,'Document.GetTextSelections')
    def test_foreign_document_endpoint_refused(self):
        self.ranges[0].end_object=types.SimpleNamespace(path='/different')
        with self.assertRaises(ValueError):w.TextAccess(self.raw).get_selection(0)
    def test_missing_document_nonbmp_legacy_range_refused(self):
        self.raw.get_parent=lambda:None
        with self.assertRaises(ValueError):w.TextAccess(self.raw).get_selection(0)
    def test_literal_object_character_not_automatically_opaque(self):
        self.raw.text='literal \ufffc';t=w.TextAccess(self.raw)
        self.assertTrue(t.representation()['plain_text_verification_supported'])



class EmbeddedBoundaryOffsets(unittest.TestCase):
    def setUp(self):
        ChromiumSelections.setUp(self);self.raw.text='abc\ufffc'
        self.child=Text();self.child.text='nested';self.child.path='/child'
        self.child.get_role_name=lambda:'section';self.child.get_parent=lambda:self.raw
        self.child.get_interfaces=lambda:['Text'];self.child.get_text_iface=lambda:self.child
        self.raw.get_interfaces=lambda:['Hypertext'];self.raw.get_hypertext_iface=lambda:self.raw
        link=types.SimpleNamespace(get_object=lambda _:self.child,get_start_index=lambda:3,get_end_index=lambda:4)
        w.Atspi.Hypertext=types.SimpleNamespace(get_n_links=lambda _:1,get_link=lambda *_:link)
    def tearDown(self):ChromiumSelections.tearDown(self)
    def test_child_start_maps_to_object_start(self):self.assertEqual(w.TextAccess(self.raw).document_offset(self.child,0,False),3)
    def test_child_end_maps_to_object_end(self):self.assertEqual(w.TextAccess(self.raw).document_offset(self.child,6,True),4)
    def test_child_interior_is_not_guessed(self):
        with self.assertRaises(ValueError):w.TextAccess(self.raw).document_offset(self.child,2,True)
    def test_empty_child_uses_endpoint_direction(self):
        self.child.text='';t=w.TextAccess(self.raw);self.assertEqual(t.document_offset(self.child,0,False),3);self.assertEqual(t.document_offset(self.child,0,True),4)

class FocusRequest(unittest.TestCase):
    def run_focus(self,grab,states):
        node=types.SimpleNamespace(path='/field',get_component_iface=lambda:types.SimpleNamespace(grab_focus=grab))
        current={'role':'entry','name':'Input','start':'1','states':['focused','enabled','showing'],'interfaces':['Component'],'protected':False}
        with patch.object(w,'candidates',return_value=[(node,0)]),patch.object(w,'describe',return_value=current),patch.object(w,'states_of',return_value=states):
            return w.main({'op':'focus','pid':42,'target':{**current,'root_path':'/root','root_bus_guid':'a'*32,'path':'/field'}})
    def test_focus_request_occurs_even_if_accessibility_says_focused(self):
        grab=__import__('unittest').mock.Mock(return_value=True);r=self.run_focus(grab,{'focused'});grab.assert_called_once();self.assertEqual(r['effect'],'verified')
    def test_unsupported_request_retains_only_observed_focus(self):
        grab=__import__('unittest').mock.Mock(side_effect=RuntimeError('unsupported'));r=self.run_focus(grab,{'focused'});self.assertTrue(r['focused']);self.assertFalse(r['accepted'])
    def test_unsupported_unfocused_request_is_not_verified(self):
        grab=__import__('unittest').mock.Mock(side_effect=RuntimeError('unsupported'))
        with self.assertRaises(RuntimeError):self.run_focus(grab,set())

class TextBudgets(unittest.TestCase):
    def test_oversized_provider_refused_before_read(self):
        raw=Text();raw.text='x'*2_000_001
        with patch.object(w.Atspi,'Text',Text,create=True),patch.object(Text,'get_text') as read:
            with self.assertRaises(w.VerificationLimit):w.TextAccess(raw)
            read.assert_not_called()
    def test_oversized_codepoint_read_is_typed(self):
        raw=Text();raw.text='x'*1_000_001
        with patch.object(w.Atspi,'Text',Text,create=True):
            with self.assertRaises(w.VerificationLimit):w.TextAccess(raw)
    def test_budget_error_before_mutation(self):
        with patch.object(w,'main',side_effect=w.VerificationLimit('private contents')):
            r=w.dispatch({'op':'set','_mutation_started':True})
        self.assertEqual(r['error'],'VERIFICATION_LIMIT');self.assertEqual(r['effect'],'none');self.assertNotIn('private',str(r))
    def test_budget_error_after_mutation(self):
        def operation(req):req['_mutation_started']=True;raise w.VerificationLimit('private contents')
        with patch.object(w,'main',side_effect=operation):r=w.dispatch({'op':'set'})
        self.assertEqual(r['effect'],'uncertain')
    def test_native_errors_never_echo_contents(self):
        with patch.object(w,'main',side_effect=RuntimeError('private contents')):
            for op in ('read','insert','set','secret'):
                r=w.dispatch({'op':op});self.assertNotIn('private',str(r));self.assertEqual(r['error'],'ACCESSIBILITY_ERROR')
    def run_set(self,raw):
        raw.path='/field'
        current={'role':'entry','name':'Input','start':'1','states':['editable','enabled','showing'],'interfaces':['Text','EditableText'],'protected':False}
        with patch.object(w.Atspi,'Text',Text,create=True),patch.object(w,'candidates',return_value=[(raw,0)]),patch.object(w,'describe',return_value=current):
            return w.dispatch({'op':'set','pid':42,'text':'new','target':{**current,'root_path':'/root','root_bus_guid':'a'*32,'path':'/field'}})
    def test_set_refuses_oversized_existing_content_before_edit(self):
        raw=Text();raw.text='x'*2_000_001;raw.set_text_contents=unittest.mock.Mock()
        r=self.run_set(raw);self.assertEqual(r['error'],'VERIFICATION_LIMIT');self.assertEqual(r['effect'],'none');raw.set_text_contents.assert_not_called()
    def test_set_oversized_provider_result_is_uncertain(self):
        raw=Text()
        def grow(text):raw.text='x'*2_000_001;return True
        raw.set_text_contents=grow
        r=self.run_set(raw);self.assertEqual(r['error'],'VERIFICATION_LIMIT');self.assertEqual(r['effect'],'uncertain')

if __name__=='__main__':unittest.main()
