"""A cropped display name must not weaken the private stale-target check."""
import types
import unittest
from unittest.mock import Mock, patch
from test_semantic import load_worker
from luda.desktop import Desktop
w=load_worker()
class Node:
 path='/same-path'
 def __init__(self,name):self.name=name;self.reads=0
 def get_interfaces(self):return []
 def get_state_set(self):return types.SimpleNamespace(get_states=lambda:[types.SimpleNamespace(value_nick=s) for s in ['enabled','showing']])
 def get_role_name(self):return 'entry'
 def get_name(self):self.reads+=1;return self.name
class Names(unittest.TestCase):
 def describe(self,node):
  with patch.object(w,'identity',return_value='start'):return w.describe(node,42)
 def test_suffix_after_public_limit_changes_private_identity(self):
  a=self.describe(Node('a'*300+'first'));b=self.describe(Node('a'*300+'second'))
  self.assertEqual(a['name'],b['name']);self.assertNotEqual(a['name_fingerprint'],b['name_fingerprint'])
 def test_reused_path_with_changed_cropped_suffix_is_stale_before_action(self):
  node=Node('a'*300+'first');target={**self.describe(node),'root_path':'/root','root_bus_guid':'a'*32};node.name='a'*300+'second'
  with patch.object(w,'identity',return_value='start'),patch.object(w,'candidates',return_value=[(node,0)]),patch.object(w,'semantic') as semantic:
   result=w.dispatch({'op':'focus','pid':42,'target':target})
  self.assertEqual(result['error'],'STALE_TARGET');semantic.assert_not_called()
 def test_name_budget_applies_to_encoded_bytes(self):
  self.assertEqual(len(w.bounded_name_identity(Node('a'*1_048_576),False)[0]),300)
  for name in ['a'*1_048_577,'😀'*262145]:
   with self.assertRaises(w.IdentityLimit):w.bounded_name_identity(Node(name),False)
 def test_protected_name_never_read_or_hashed(self):
  node=Node('sensitive');self.assertEqual(w.bounded_name_identity(node,True),('[protected]',None));self.assertEqual(node.reads,0)
 def test_identity_budget_diagnostic_contains_no_application_contents(self):
  with patch.object(w,'main',side_effect=w.IdentityLimit('private content')):
   result=w.dispatch({'op':'choose'})
  self.assertEqual(result['error'],'TARGET_IDENTITY_UNAVAILABLE');self.assertEqual(result['effect'],'none');self.assertNotIn('private content',str(result))
 def test_public_inspection_hides_digest_but_handle_retains_it(self):
  desktop=Desktop.__new__(Desktop);desktop.elements={}
  desktop.target_window=Mock(return_value={'pid':42,'start':'1','bounds':{},'frame_bounds':{},'title':'Fixture'})
  node={'path':'/field','parent_path':None,'root_path':'/root','root_bus_guid':'a'*32,'start':'1','name':'label','name_fingerprint':'private-digest','root_provider':':1.42'}
  desktop.ax=Mock(return_value={'nodes':[node]})
  result=desktop.inspect('window');public=result['nodes'][0]
  self.assertNotIn('name_fingerprint',public)
  self.assertNotIn('root_provider',public)
  self.assertNotIn('root_bus_guid',public)
  self.assertEqual(desktop.elements[public['element_id']]['node']['root_bus_guid'],'a'*32)
  self.assertEqual(desktop.elements[public['element_id']]['node']['root_provider'],':1.42')
  self.assertEqual(desktop.elements[public['element_id']]['node']['name_fingerprint'],'private-digest')
 def test_unreadable_name_marks_inspection_incomplete(self):
  node=Node('label');node.app=types.SimpleNamespace(bus_name=':1.42');node.get_interfaces=lambda:['Component']
  node.get_component_iface=lambda:types.SimpleNamespace(get_extents=lambda _:types.SimpleNamespace(x=0,y=0,width=100,height=100))
  bounds={'x':0,'y':0,'width':100,'height':100}
  with patch.object(w.Atspi,'CoordType',types.SimpleNamespace(SCREEN=0),create=True),patch.object(w,'candidates',side_effect=[[(node,1)],[(node,0)]]),patch.object(w,'describe',side_effect=w.IdentityLimit('too large')):
   result=w.dispatch({'op':'inspect','pid':42,'bounds':bounds,'frame_bounds':bounds})
  self.assertTrue(result['truncated']);self.assertEqual(result['unreadable_nodes'],1);self.assertEqual(result['nodes'],[])
if __name__=='__main__':unittest.main()
