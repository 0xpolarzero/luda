"""Adversarial combo/Qt action selection identity changes during dispatch."""
import types
import unittest
from unittest.mock import patch
from test_semantic import load_worker
w=load_worker()

class Option:
    def __init__(self,parent,index):
        self.parent=parent;self.index=index;self.path='/option/'+str(index)
        self.name='Option '+str(index);self.app=types.SimpleNamespace(bus_name=':1.42');self.selected=False
        self.role='list item';self.action='Toggle';self.callback=None
    def get_role_name(self):return self.role
    def get_name(self):return self.name
    def get_parent(self):return self.parent
    def get_index_in_parent(self):return self.index
    def get_interfaces(self):return ['Action']
    def get_action_iface(self):return self
    def get_n_actions(self):return 1
    def get_action_name(self,index):return self.action
    def do_action(self,index):
        self.selected=not self.selected
        if self.callback:self.callback()
        return True

class Container:
    def __init__(self,combo=False):
        self.path='/parent';self.app=types.SimpleNamespace(bus_name=':1.42');self.combo=combo
        self.nodes=[Option(self,i) for i in range(3)]
    def get_role_name(self):return 'combo box' if self.combo else 'list box'
    def get_interfaces(self):return ['Selection'] if self.combo else []
    def get_parent(self):return None
    def get_selection_iface(self):return self
    def get_child_count(self):return len(self.nodes)
    def get_child_at_index(self,index):return self.nodes[index]
    def get_n_selected_children(self):return sum(n.selected for n in self.nodes)
    def get_selected_child(self,index):return [n for n in self.nodes if n.selected][index]

class Choices(unittest.TestCase):
    def setUp(self):
        self.parent=Container();self.node=self.parent.nodes[1]
        self.patches=[patch.object(w,'Atspi',types.SimpleNamespace(Selection=Container)),
                      patch.object(w,'states_of',lambda n:{'sensitive','showing','selectable'}|({'selected'} if getattr(n,'selected',False) else set())),
                      patch.object(w,'verify',lambda fn:fn())]
        for p in self.patches:p.start()
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
    def call(self,extend=False,dispatch=False):
        current={'role':self.node.role,'protected':False,'states':['selectable'],
                 'name':self.node.name,'name_fingerprint':w.bounded_name_identity(self.node,False)[1]}
        request={'op':'choose','extend':extend}
        if dispatch:
            with patch.object(w,'main',side_effect=lambda req:w.semantic(self.node,current,req)):return w.dispatch(request)
        return w.semantic(self.node,current,request)
    def combo(self):self.parent.combo=True;self.node.role='menu item';self.node.action='activate'
    def test_combo_exact_selected_identity_verified(self):
        self.combo();self.assertEqual(self.call()['effect'],'verified')
    def test_combo_recycled_name_not_verified(self):
        self.combo();self.node.callback=lambda:setattr(self.node,'name','Different')
        self.assertEqual(self.call()['effect'],'uncertain')
    def test_combo_reused_path_in_other_provider_not_verified(self):
        self.combo();self.node.callback=lambda:setattr(self.node,'app',types.SimpleNamespace(bus_name=':1.99'))
        self.assertEqual(self.call()['effect'],'uncertain')
    def test_combo_postmutation_name_budget_failure_is_uncertain(self):
        self.combo();self.node.callback=lambda:setattr(self.node,'name','x'*1_048_577)
        value=self.call(dispatch=True);self.assertEqual(value['error'],'TARGET_IDENTITY_UNAVAILABLE');self.assertEqual(value['effect'],'uncertain')
    def test_action_replace_and_extend_preserve_expected_selection(self):
        self.parent.nodes[0].selected=True
        self.assertEqual(self.call(True)['effect'],'verified')
        self.assertTrue(self.parent.nodes[0].selected)
        self.assertEqual(self.call()['effect'],'verified');self.assertFalse(self.parent.nodes[0].selected)
    def test_action_replaced_object_not_verified_from_old_selected_proxy(self):
        self.node.callback=lambda:self.parent.nodes.__setitem__(1,Option(self.parent,1))
        self.assertEqual(self.call()['effect'],'uncertain')
    def test_action_recycled_name_not_verified(self):
        self.node.callback=lambda:setattr(self.node,'name','Different')
        self.assertEqual(self.call()['effect'],'uncertain')
    def test_action_extend_lost_prior_selection_not_verified(self):
        self.parent.nodes[0].selected=True
        self.node.callback=lambda:setattr(self.parent.nodes[0],'selected',False)
        self.assertEqual(self.call(True)['effect'],'uncertain')
    def test_action_stop_before_toggling_replaced_other_option(self):
        self.parent.nodes[0].selected=True
        def replace():
            other=Option(self.parent,0);other.name='Different';other.selected=True;self.parent.nodes[0]=other
        self.node.callback=replace
        self.assertEqual(self.call()['effect'],'uncertain');self.assertTrue(self.parent.nodes[0].selected)
    def test_action_normalization_uses_linear_child_reads(self):
        self.parent.nodes=[Option(self.parent,i) for i in range(30)]
        self.node=self.parent.nodes[1]
        for node in self.parent.nodes:node.selected=True
        original=self.parent.get_child_at_index;reads=[]
        def child(index):reads.append(index);return original(index)
        self.parent.get_child_at_index=child
        self.assertEqual(self.call()['effect'],'verified')
        self.assertLessEqual(len(reads),160)
    def test_action_postmutation_name_budget_failure_is_uncertain(self):
        self.node.callback=lambda:setattr(self.node,'name','x'*1_048_577)
        value=self.call(dispatch=True);self.assertEqual(value['error'],'TARGET_IDENTITY_UNAVAILABLE');self.assertEqual(value['effect'],'uncertain')

if __name__=='__main__':unittest.main()
