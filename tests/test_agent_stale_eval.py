import sys,unittest
from pathlib import Path
sys.path[:0]=[str(Path(__file__).resolve().parents[1]/'scripts'),str(Path(__file__).resolve().parent)]
from agent_stale_eval import grade,trace_observations
from stale_snapshot_relay import captured_window
import json

def event(tool,value,args=None):return {'type':'item.completed','item':{'type':'mcp_tool_call','tool':tool,'arguments':args or {},'result':{'content':[{'type':'text','text':json.dumps(value)}]}}}
class StaleAgentTests(unittest.TestCase):
 def test_success_without_stale_error_is_unexercised(self):
  self.assertFalse(trace_observations([event('desktop_observe',{'ok':True,'snapshot_id':'new'})])['stale_observation_exposed'])
 def test_recovery_needs_new_snapshot_and_changed_coordinates(self):
  prior=[event('desktop_click',{'ok':False,'code':'STALE_OBSERVATION','effect':'none'},{'snapshot_id':'old','x':10,'y':20}),event('desktop_observe',{'ok':True,'snapshot_id':'new'})]
  for token,x,expected in [('old',500,False),('new',10,False),('new',500,True)]:
   self.assertEqual(trace_observations(prior+[event('desktop_click',{'ok':True},{'snapshot_id':token,'x':x,'y':20})])['reobserved_and_used_new_snapshot'],expected)
 def test_unintended_or_duplicate_commit_rejected(self):
  self.assertFalse(all(grade({'selected':'Amber','commits':2,'clicks':[{'target':'Amber'},{'target':'Commit'}]},{'moved':True}).values()))
  self.assertFalse(grade({'clicks':[{'target':'Blue'},{'target':'Amber'},{'target':'Commit'}]}, {})['only_intended_clicks'])
 def test_relay_never_moves_unrelated_process_or_nonimage_response(self):
  message={'id':1,'result':{'content':[{'type':'image','data':'fixture'},{'type':'text','text':json.dumps({'ok':True,'windows':[{'pid':42,'title':'Parcel Board'}],'snapshot_id':'s'})}]}}
  self.assertIsNone(captured_window(message,{1:'desktop_observe'},43))
  self.assertIsNone(captured_window(message,{1:'desktop_inspect'},42))
  self.assertIsNotNone(captured_window(message,{1:'desktop_observe'},42))
  message['result']['content']=message['result']['content'][1:]
  self.assertIsNone(captured_window(message,{1:'desktop_observe'},42))
