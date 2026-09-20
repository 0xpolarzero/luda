"""Selecting an index must not verify a different or recycled option."""
import types
import unittest
from unittest.mock import patch
from test_semantic import w,SelectionProvider


class SelectionIdentity(unittest.TestCase):
    def setUp(self):
        self.parent=SelectionProvider();self.node=self.parent.nodes[1]
        self.node.get_parent=lambda:self.parent
        self.node.get_name=lambda:'Original option'
        self.current={'protected':False,'role':'list item','states':[],
                      'name':'Original option','name_fingerprint':w.bounded_name_identity(self.node,False)[1]}
        self.patches=[patch.object(w,'Atspi',types.SimpleNamespace(Selection=SelectionProvider)),
                      patch.object(w,'states_of',return_value={'sensitive','showing'}),
                      patch.object(w,'verify',lambda fn,**kw:fn())]
        for p in self.patches:p.start()
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
    def choose(self):return w.semantic(self.node,self.current,{'op':'choose'})
    def test_replaced_child_at_selected_index_is_not_verified(self):
        def select(index):
            self.parent.selected.add(index)
            self.parent.nodes[index]=types.SimpleNamespace(path='/replacement',get_index_in_parent=lambda:index,app=self.node.app,get_role_name=lambda:'list item',get_name=lambda:'Replacement')
            return True
        selected=patch.object(SelectionProvider,'select_child',lambda parent,index:select(index));selected.start();self.addCleanup(selected.stop)
        self.assertEqual(self.choose()['effect'],'uncertain')
        self.assertEqual(self.parent.selected,{1},'must not deselect an unobserved replacement')
    def test_recycled_selected_name_is_not_verified(self):
        def select(index):
            self.parent.selected.add(index)
            self.node.get_name=lambda:'Different option'
            return True
        selected=patch.object(SelectionProvider,'select_child',lambda parent,index:select(index));selected.start();self.addCleanup(selected.stop)
        self.assertEqual(self.choose()['effect'],'uncertain')
    def test_changed_provider_with_same_path_is_not_verified(self):
        def select(index):
            self.parent.selected.add(index)
            self.node.app=types.SimpleNamespace(bus_name=':1.99')
            return True
        selected=patch.object(SelectionProvider,'select_child',lambda parent,index:select(index));selected.start();self.addCleanup(selected.stop)
        self.assertEqual(self.choose()['effect'],'uncertain')
    def test_extend_does_not_verify_lost_prior_selection(self):
        self.parent.selected={0}
        def select(index):
            self.parent.selected={index}
            return True
        selected=patch.object(SelectionProvider,'select_child',lambda parent,index:select(index));selected.start();self.addCleanup(selected.stop)
        result=w.semantic(self.node,self.current,{'op':'choose','extend':True})
        self.assertEqual(result['effect'],'uncertain')
    def test_identity_budget_failure_after_selection_stays_uncertain(self):
        def select(index):
            self.parent.selected.add(index)
            self.node.get_name=lambda:'x'*1_048_577
            return True
        selected=patch.object(SelectionProvider,'select_child',lambda parent,index:select(index));selected.start();self.addCleanup(selected.stop)
        with patch.object(w,'main',side_effect=lambda req:w.semantic(self.node,self.current,req)):
            result=w.dispatch({'op':'choose'})
        self.assertEqual(result['error'],'TARGET_IDENTITY_UNAVAILABLE')
        self.assertEqual(result['effect'],'uncertain')

if __name__=='__main__':unittest.main()
