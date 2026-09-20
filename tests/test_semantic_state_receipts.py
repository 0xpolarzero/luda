"""A verified receipt must report the same provider observation it checked."""
import unittest
from unittest.mock import Mock, patch
from test_semantic import load_worker


class SemanticStateReceiptTests(unittest.TestCase):
    def setUp(self):
        self.worker=load_worker()

    def test_numeric_receipt_does_not_reread_after_verified_observation(self):
        value=Mock();value.get_minimum_value.return_value=0;value.get_maximum_value.return_value=10
        value.set_current_value.return_value=True;value.get_current_value.side_effect=[5,9]
        node=Mock();node.get_value_iface.return_value=value
        result=self.worker.semantic(node,{'interfaces':['Value']},{'op':'value','value':5})
        self.assertEqual(result['effect'],'verified');self.assertTrue(result['exact_match'])
        self.assertEqual(result['actual_value'],5);self.assertEqual(value.get_current_value.call_count,1)

    def test_check_and_expand_receipts_do_not_reread_after_verification(self):
        for op,key,state in [('check','checked','checked'),('expand','expanded','expanded')]:
            with self.subTest(op=op):
                node=Mock();node.get_action_iface.return_value.do_action.return_value=True
                current={'interfaces':[],'role':'check box','states':['expandable'],'actions':['toggle']}
                with patch.object(self.worker,'states_of',side_effect=[set(),{state},set()]) as read:
                    result=self.worker.semantic(node,current,{'op':op,key:True})
                self.assertEqual(result['effect'],'verified');self.assertTrue(result[key]);self.assertEqual(read.call_count,2)

    def test_failed_value_uses_last_unsuccessful_observation(self):
        value=Mock();value.get_minimum_value.return_value=0;value.get_maximum_value.return_value=10
        value.set_current_value.return_value=False;value.get_current_value.side_effect=[4,5]
        node=Mock();node.get_value_iface.return_value=value
        with patch.object(self.worker,'verify',side_effect=lambda predicate:predicate()):
            result=self.worker.semantic(node,{'interfaces':['Value']},{'op':'value','value':5})
        self.assertEqual(result['effect'],'uncertain');self.assertFalse(result['exact_match'])
        self.assertEqual(result['actual_value'],4);value.set_current_value.assert_called_once_with(5)

    def test_state_noop_observes_once_and_dispatches_nothing(self):
        for op,key in [('check','checked'),('expand','expanded')]:
            for desired in (False,True):
                with self.subTest(op=op,desired=desired):
                    node=Mock();current={'interfaces':[],'role':'check box','states':['expandable'],'actions':['toggle']}
                    with patch.object(self.worker,'states_of',return_value={key} if desired else set()) as read:
                        result=self.worker.semantic(node,current,{'op':op,key:desired})
                    self.assertEqual(result[key],desired);self.assertFalse(result['changed'])
                    self.assertEqual(result['effect'],'verified');read.assert_called_once_with(node)
                    node.get_action_iface.assert_not_called()

    def test_failed_action_keeps_last_mismatched_state_not_later_success(self):
        for op,key in [('check','checked'),('expand','expanded')]:
            with self.subTest(op=op):
                node=Mock();node.get_action_iface.return_value.do_action.return_value=False
                current={'interfaces':[],'role':'check box','states':['expandable'],'actions':['toggle']}
                with patch.object(self.worker,'states_of',side_effect=[set(),set(),{key}]) as read,patch.object(self.worker,'verify',side_effect=lambda predicate:predicate()):
                    result=self.worker.semantic(node,current,{'op':op,key:True})
                self.assertEqual(result['effect'],'uncertain');self.assertFalse(result[key]);self.assertEqual(read.call_count,2)
                node.get_action_iface.return_value.do_action.assert_called_once_with(0)

    def test_uncheck_and_collapse_report_verified_absence_without_reread(self):
        for op,key in [('check','checked'),('expand','expanded')]:
            with self.subTest(op=op):
                node=Mock();node.get_action_iface.return_value.do_action.return_value=True
                current={'interfaces':[],'role':'check box','states':['expandable'],'actions':['toggle']}
                with patch.object(self.worker,'states_of',side_effect=[{key},set(),{key}]) as read:
                    result=self.worker.semantic(node,current,{'op':op,key:False})
                self.assertEqual(result['effect'],'verified');self.assertFalse(result[key]);self.assertEqual(read.call_count,2)
