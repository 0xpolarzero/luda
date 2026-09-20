import json
import types
import unittest
from unittest.mock import Mock, patch
from test_semantic import load_worker, Text


class NumericBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.w=load_worker();self.node=Mock();self.v=self.node.get_value_iface.return_value
        self.v.get_minimum_value.return_value=0;self.v.get_maximum_value.return_value=10
        self.v.get_current_value.return_value=5;self.v.get_minimum_increment.return_value=1
        self.v.set_current_value.return_value=True

    def call(self):
        return self.w.semantic(self.node,{'interfaces':['Value']},{'op':'value','value':5})

    def test_invalid_ranges_refuse_before_mutation(self):
        for low,high in [(float('nan'),10),(0,float('inf')),(11,10),(False,10)]:
            with self.subTest(low=low,high=high):
                self.v.get_minimum_value.return_value=low;self.v.get_maximum_value.return_value=high
                r=self.call();self.assertEqual((r['error'],r['effect']),('VALUE_UNVERIFIABLE','none'))
                json.dumps(r,allow_nan=False);self.v.set_current_value.assert_not_called()

    def test_invalid_or_unreadable_postread_is_uncertain_and_private(self):
        for value in (float('nan'),float('inf'),float('-inf'),None,'private',RuntimeError('private')):
            with self.subTest(kind=type(value).__name__):
                self.v.get_current_value.side_effect=value if isinstance(value,Exception) else None
                self.v.get_current_value.return_value=value
                r=self.call();self.assertEqual((r['error'],r['effect']),('VALUE_UNVERIFIABLE','uncertain'))
                self.assertNotIn('private',json.dumps(r,allow_nan=False))
        self.assertEqual(self.v.set_current_value.call_count,6)

    def test_unused_increment_does_not_block_mutation(self):
        self.v.get_minimum_increment.side_effect=RuntimeError('unused')
        self.assertEqual(self.call()['effect'],'verified');self.v.get_minimum_increment.assert_not_called()

    def test_inspect_keeps_node_but_omits_invalid_numeric_block(self):
        self.node.path='/node';self.node.get_interfaces.return_value=['Value']
        self.node.get_role_name.return_value='spin button';self.node.get_state_set.return_value.get_states.return_value=[]
        for method in ('get_current_value','get_minimum_value','get_maximum_value','get_minimum_increment'):
            with self.subTest(method=method),patch.object(self.v,method,return_value=float('nan')),patch.object(self.w,'identity',return_value='start'),patch.object(self.w,'bounded_name_identity',return_value=('control','hash')):
                r=self.w.describe(self.node,42)
                self.assertEqual(r['name'],'control');self.assertNotIn('value',r)
                self.assertEqual(r['value_error'],'VALUE_UNVERIFIABLE');json.dumps(r,allow_nan=False)

    def test_insert_count_uses_successful_or_failed_verification_text(self):
        for ignored in (False,True):
            with self.subTest(ignored=ignored):
                t=Text();t.ignore_insert=ignored
                old=self.w.TextAccess.get_character_count
                def count(access):
                    if t.edits:t.text+='CHANGED'
                    return old(access)
                with patch.object(self.w,'Atspi',types.SimpleNamespace(Text=Text)),patch.object(self.w,'verify',lambda fn,**kw:fn()),patch.object(self.w.TextAccess,'get_character_count',count):
                    r=self.w.semantic(t,{'protected':False,'interfaces':['Text','EditableText'],'states':['editable','enabled','showing']},{'op':'insert','text':'X'})
                self.assertEqual(r['actual_characters'],3 if ignored else 4)
                self.assertEqual(r['exact_match'],not ignored)
                json.dumps(r,allow_nan=False)

    def test_verified_caret_receipt_uses_observed_offset(self):
        class ChangingCaret(Text):
            def get_caret_offset(self):
                result=self.caret
                if result==2:self.caret=0
                return result
        t=ChangingCaret()
        with patch.object(self.w,'Atspi',types.SimpleNamespace(Text=ChangingCaret)),patch.object(self.w,'verify',lambda fn,**kw:fn()):
            result=self.w.semantic(t,{'protected':False,'interfaces':['Text','EditableText'],'states':['editable','enabled','showing']},{'op':'insert','text':'X'})
        self.assertTrue(result['caret_verified']);self.assertEqual(result['caret_offset'],2)
        self.assertEqual(t.caret,0)  # Later state differs; receipt is historical.
