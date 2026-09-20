import sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import agent_range_eval as subject
class RangeAgentOracleTests(unittest.TestCase):
 def test_final_set_does_not_hide_dropped_prior_selection(self):
  v=subject.grade({'selected_ids':[2,3,4,6],'events':[[2],[2,3,4,6]]});self.assertTrue(v['exact_selected_ids']);self.assertFalse(v['initial_record_preserved'])
 def test_unrequested_transient_record_is_not_ignored(self):
  v=subject.grade({'selected_ids':[2,3,4,6],'events':[[1,6],[2,3,4,6]]});self.assertFalse(v['no_unrequested_selection'])
 def test_additive_monotonic_selection_matches_intent(self):
  self.assertTrue(all(subject.grade({'selected_ids':[2,3,4,6],'events':[[2,6],[2,3,6],[2,3,4,6]]}).values()))
 def test_range_requires_observed_same_group_and_explicit_extend(self):
  def e(tool,arguments={},result={}):return {'type':'item.completed','item':{'type':'mcp_tool_call','tool':tool,'arguments':arguments,'result':result}}
  import json
  inspect=e('desktop_inspect',result={'content':[{'type':'text','text':json.dumps({'nodes':[{'element_id':'a'},{'element_id':'b'}]})}]})
  choose=e('desktop_choose',{'element_id':'a','range_end_id':'b','extend':True});self.assertTrue(subject.trace_observations([inspect,choose])['range_add_discovered']);self.assertFalse(subject.trace_observations([choose])['range_add_discovered']);choose['item']['arguments']['extend']=False;self.assertFalse(subject.trace_observations([inspect,choose])['range_add_discovered'])
 def test_semantic_receipt_requires_complete_exact_public_selected_set(self):
  import json
  value={'ok':True,'available':True,'truncated':False,'unreadable_nodes':0,'unreadable_branches':0,'window_id':'w','truncation':{'result_or_time_limit':False,'budget_pruned':False,'depth_pruned':False,'unreadable_branches':0},'nodes':[{'name':f'Record {n:03}','role':'table cell','states':['selected']} for n in (2,3,4,6)]}
  def call():return {'tool':'desktop_inspect','arguments':{'window_id':'w','role':'table cell','states':['selected']},'result':{'content':[{'type':'text','text':json.dumps(value)}]}}
  self.assertTrue(subject.semantic_receipt([call()]));self.assertFalse(subject.semantic_receipt([]))
  value['nodes'][0]['name']='Record 001';self.assertFalse(subject.semantic_receipt([call()]));value['nodes'][0]['name']='Record 002'
  value['truncated']=True;self.assertFalse(subject.semantic_receipt([call()]));value['truncated']=False
  c=call();c['arguments']['name']='Record';self.assertFalse(subject.semantic_receipt([c]))
  self.assertFalse(subject.semantic_receipt([call(),{'tool':'desktop_choose'}]))
  value['unreadable_branches']=1;self.assertFalse(subject.semantic_receipt([call()]))
if __name__=='__main__':unittest.main()
