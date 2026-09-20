import unittest
from cancellation_finalization import finalized_cancellation
class CancellationFinalizationTests(unittest.TestCase):
 def event(self,**kwargs):return dict(operation_id='new',method='type_text',ok=False,code='CANCELLED',effect='uncertain',**kwargs)
 def test_new_final_event_and_cleared_recovery_are_required(self):
  event=self.event();self.assertEqual(finalized_cancellation({'recovering':False,'operations':[event]},{'old'}),event)
  self.assertIsNone(finalized_cancellation({'recovering':True,'operations':[event]},{'old'}))
  self.assertIsNone(finalized_cancellation({'recovering':False,'operations':[]},{'old'}))
 def test_old_or_unrelated_completion_does_not_authorize_reopen(self):
  event=self.event();self.assertIsNone(finalized_cancellation({'recovering':False,'operations':[event]},{'new'}))
  event['method']='inspect';self.assertIsNone(finalized_cancellation({'recovering':False,'operations':[event]},set()))
 def test_non_cancelled_or_ambiguous_completion_refused(self):
  event=self.event();event['code']='TEXT_MISMATCH';self.assertIsNone(finalized_cancellation({'recovering':False,'operations':[event]},set()))
  event=self.event();self.assertIsNone(finalized_cancellation({'recovering':False,'operations':[event,dict(event,operation_id='other')]},set()))
