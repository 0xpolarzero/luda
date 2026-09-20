import importlib.util,sys,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from agent_save_eval import grade,PAYLOAD,trace_observations
class SaveOracleTests(unittest.TestCase):
 def test_exact_single_commit(self):
  self.assertTrue(all(grade({'text':PAYLOAD,'submissions':1,'stall_started':10,'committed_monotonic':30},{'submissions':1}).values()))
 def test_late_duplicate_rejected(self):
  self.assertFalse(grade({'text':PAYLOAD,'submissions':1,'stall_started':10,'committed_monotonic':30},{'submissions':2})['one_submission'])
 def test_missing_or_transformed_text_rejected(self):
  self.assertFalse(all(grade({},{}).values()))
  self.assertFalse(grade({'text':PAYLOAD.rstrip()},{})['exact_text'])

class ObservationGradeTests(unittest.TestCase):
 def test_structured_error_without_iserror(self):
  event={'type':'item.completed','item':{'type':'mcp_tool_call','tool':'desktop_inspect','result':{'content':[{'type':'text','text':'{"ok":false,"code":"ACCESSIBILITY_UNAVAILABLE"}'}]}}}
  self.assertTrue(trace_observations([event])['observation_error_exposed'])
 def test_image_requires_explicit_review(self):
  event={'type':'item.completed','item':{'type':'mcp_tool_call','tool':'desktop_observe','result':{'content':[{'type':'image','data':'synthetic'}]}}}
  result=trace_observations([event]);self.assertTrue(result['receipt_visual_review_required']);self.assertFalse(result['saved_receipt_exposed_as_text'])
