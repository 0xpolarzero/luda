import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from agent_terminal_eval import grade,PAYLOAD,trace_observations
class TerminalAgentOracleTests(unittest.TestCase):
 def test_exact_terminal_translation_and_real_held_dialog(self):
  self.assertTrue(all(grade({'hex':PAYLOAD.replace('\n','\r').encode().hex()},{'dialog_observed':True,'preapproval_hex':''}).values()))
 def test_duplicate_or_extra_enter_rejected(self):
  body=PAYLOAD.replace('\n','\r').encode()
  for value in (body+body,body+b'\r'):
   self.assertFalse(grade({'hex':value.hex()},{})['exact_terminal_bytes'])
 def test_unobserved_or_already_delivered_confirmation_fails(self):
  for state in ({},{'dialog_observed':True,'preapproval_hex':'61'}):
   self.assertFalse(all(grade({'hex':PAYLOAD.replace('\n','\r').encode().hex()},state).values()))
 def test_agent_final_claim_cannot_promote_receipt(self):
  result=trace_observations([{'type':'item.completed','item':{'type':'agent_message','text':'Verified receipt'}}])
  self.assertTrue(result['receipt_visual_review_required']);self.assertEqual(result['agent_paste_calls'],0)
