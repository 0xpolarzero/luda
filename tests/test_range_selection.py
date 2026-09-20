import types,unittest
from unittest.mock import patch
from test_semantic import load_worker
w=load_worker()
def bounds(x=0,y=0,width=200,height=400):return types.SimpleNamespace(x=x,y=y,width=width,height=height)
class Frame:
 path='/window';name='Window';app=types.SimpleNamespace(bus_name=':1.42');states={'active','showing','enabled'}
 def get_interfaces(self):return ['Component']
 def get_component_iface(self):return self
 def get_extents(self,_):return bounds()
 def get_role_name(self):return 'frame'
 def get_name(self):return self.name
 def get_parent(self):return None
class Table(Frame):
 path='/table';name='Records'
 def __init__(self):
  self.frame=Frame();self.states={'showing','enabled','multiselectable'};self.cells=[Cell(self,i) for i in range(6)];self.rows=set();self.calls=[];self.callback=None;self.ignore=False
 def get_interfaces(self):return ['Table','Component']
 def get_role_name(self):return 'table'
 def get_parent(self):return self.frame
 def get_table_iface(self):return self
 def get_accessible_at(self,row,col):return self.cells[row]
 def get_selected_rows(self):return sorted(self.rows)
 def add_row_selection(self,index):
  self.calls.append(('add',index))
  if not self.ignore:self.rows.add(index)
  if self.callback:self.callback()
  return True
 def remove_row_selection(self,index):
  self.calls.append(('remove',index));self.rows.discard(index)
  if self.callback:self.callback()
  return True
class Cell(Frame):
 def __init__(self,table,index):self.table=table;self.name='Record '+str(index);self.path='/cell/'+str(index);self.states={'showing','enabled','selectable'};self.hidden=False
 def get_role_name(self):return 'table cell'
 def get_interfaces(self):return ['Component','TableCell']
 def get_parent(self):return self.table
 def get_table_cell(self):return self
 def get_table(self):return self.table
 def get_position(self):return True,self.table.cells.index(self),0
 def get_extents(self,_):return bounds(y=1000 if self.hidden else self.table.cells.index(self)*20,height=20)
class RangeTests(unittest.TestCase):
 def setUp(self):
  self.table=Table();self.patches=[patch.object(w,'Atspi',types.SimpleNamespace(TableCell=Cell,CoordType=types.SimpleNamespace(SCREEN=0))),patch.object(w,'states_of',lambda n:n.states),patch.object(w,'verify',lambda fn:fn()),patch.object(w,'candidates',lambda *a,**kw:((n,1) for n in [self.table.frame,self.table,*self.table.cells]))]
  for p in self.patches:p.start()
 def tearDown(self):
  for p in reversed(self.patches):p.stop()
 def observed(self,c):return {'path':c.path,'parent_path':'/table','role':'table cell','name':c.name,'name_fingerprint':w.bounded_name_identity(c,False)[1],'start':'1','root_path':'/window','root_provider':':1.42','root_bus_guid':'a'*32,'bounds_coordinates':'screen'}
 def call(self,start=1,end=3,extend=False,observations=None):
  node=self.table.cells[start];first=self.observed(node);last=self.observed(self.table.cells[end]);req={'pid':1,'target':first,'range_end':last,'range_nodes':observations or [self.observed(c) for c in self.table.cells[min(start,end):max(start,end)+1]],'extend':extend,'_range_receipt':{}}
  result=w.choose_range(node,{**first,'interfaces':node.get_interfaces()},req);self.receipt=req['_range_receipt'];return result
 def test_replace_exact_rows_and_step_receipt(self):
  self.table.rows={0,5};r=self.call();self.assertEqual(r['effect'],'verified');self.assertEqual(self.table.rows,{1,2,3});self.assertEqual([x['name'] for x in r['selected_items']],['Record 1','Record 2','Record 3']);self.assertEqual(self.receipt['progress']['verified_completed'],5)
 def test_reversed_extend_and_idempotency(self):
  self.table.rows={0};r=self.call(3,1,True);self.assertEqual(r['effect'],'verified');self.assertEqual(self.table.rows,{0,1,2,3});self.table.calls.clear();r=self.call(1,3,True);self.assertFalse(r['changed']);self.assertEqual(self.table.calls,[]);self.assertEqual(self.receipt['progress']['requested'],0)
 def test_offscreen_and_disabled_range_refuse_before_input(self):
  for kind in ['hidden','disabled']:
   with self.subTest(kind=kind):
    self.table.cells[2].hidden=kind=='hidden';self.table.cells[2].states={'showing'} if kind=='disabled' else {'showing','enabled'}
    self.assertEqual(self.call()['error'],'NOT_INTERACTABLE');self.assertEqual(self.table.calls,[])
 def test_missing_intermediate_and_duplicate_labels_refused(self):
  self.assertEqual(self.call(observations=[self.observed(self.table.cells[i]) for i in [1,3]])['error'],'STALE_TARGET');self.assertEqual(self.table.calls,[])
  self.table.cells[2].name=self.table.cells[1].name;self.assertEqual(self.call()['error'],'UNSUPPORTED');self.assertEqual(self.table.calls,[])
 def test_sort_after_first_step_stops_without_replay(self):
  self.table.callback=lambda:self.table.cells.reverse();r=self.call();self.assertEqual(r['effect'],'uncertain');self.assertEqual(r['error'],'STALE_TARGET');self.assertEqual(len(self.table.calls),1);self.assertEqual(self.receipt['progress']['current_uncertain'],1)
 def test_focus_change_after_verified_step_stops(self):
  calls=0
  def states(n):
   nonlocal calls
   if n is self.table.frame:
    calls+=1
    if calls>=6:return {'showing','enabled'}
   return n.states
  with patch.object(w,'states_of',states):r=self.call()
  self.assertEqual(r['error'],'FOCUS_CHANGED');self.assertEqual(len(self.table.calls),1);self.assertEqual(self.receipt['progress']['verified_completed'],1)
 def test_false_provider_acceptance_never_verified(self):
  self.table.ignore=True;r=self.call();self.assertEqual(r['effect'],'uncertain');self.assertEqual(r['error'],'SELECTION_UNVERIFIABLE');self.assertEqual(self.receipt['progress']['verified_completed'],0);self.assertEqual(len(self.table.calls),1)
 def test_same_path_recycled_name_refused(self):
  self.table.callback=lambda:setattr(self.table.cells[2],'name','Recycled');r=self.call();self.assertEqual(r['error'],'STALE_TARGET');self.assertEqual(len(self.table.calls),1)
 def test_huge_position_gap_refused_without_allocation(self):
  original=Cell.get_position
  with patch.object(Cell,'get_position',lambda c:(True,2**31 if c is self.table.cells[3] else original(c)[1],0)):
   self.assertEqual(self.call()['error'],'SELECTION_TOO_LARGE')
  self.assertEqual(self.table.calls,[])

 def test_missing_multiselect_hint_still_verifies_and_single_mode_stops(self):
  self.table.states.discard('multiselectable');self.assertEqual(self.call()['effect'],'verified')
  self.table.rows.clear();self.table.calls.clear()
  original=self.table.add_row_selection
  def single(index):
   self.table.rows.clear();return original(index)
  self.table.add_row_selection=single
  result=self.call();self.assertEqual(result['error'],'SELECTION_UNVERIFIABLE');self.assertEqual(result['effect'],'uncertain');self.assertEqual(self.table.rows,{2});self.assertEqual(len(self.table.calls),2);self.assertEqual(self.receipt['progress']['verified_completed'],1)
 def test_same_endpoints_different_current_interior_order_refuses(self):
  saved=[self.observed(c) for c in self.table.cells[1:5]]
  self.table.cells[2],self.table.cells[3]=self.table.cells[3],self.table.cells[2]
  self.assertEqual(self.call(1,4,observations=saved)['error'],'STALE_TARGET');self.assertEqual(self.table.calls,[])
 def test_other_column_endpoint_refuses(self):
  original=Cell.get_position
  with patch.object(Cell,'get_position',lambda c:(True,original(c)[1],1 if c is self.table.cells[3] else 0)):
   self.assertEqual(self.call()['error'],'UNSUPPORTED')
  self.assertEqual(self.table.calls,[])
 def test_reorder_during_pre_action_selected_read_refuses_without_mutation(self):
  count=0
  original=self.table.get_selected_rows
  def selected():
   nonlocal count
   count+=1
   if count==2:self.table.cells.reverse()
   return original()
  self.table.get_selected_rows=selected
  result=self.call();self.assertEqual(result['error'],'STALE_TARGET');self.assertEqual(result['effect'],'none');self.assertEqual(self.table.calls,[])
 def configure_list(self,ignore_clear=False):
  self.table.rows={0,5}
  self.table.get_interfaces=lambda:['Component','Selection']
  self.table.get_selection_iface=lambda:self.table
  self.table.get_child_at_index=lambda i:self.table.cells[i]
  for cell in self.table.cells:
   cell.get_interfaces=lambda:['Component']
   cell.get_role_name=lambda:'list item'
   cell.get_index_in_parent=lambda c=cell:self.table.cells.index(c)
  observed=self.observed;self.observed=lambda c:{**observed(c),'role':'list item'}
  def clear(p):
   p.calls.append(('clear',None))
   if not ignore_clear:p.rows.clear()
   return True
  return types.SimpleNamespace(get_n_selected_children=lambda p:len(p.rows),get_selected_child=lambda p,i:p.cells[sorted(p.rows)[i]],select_child=lambda p,i:p.add_row_selection(i),clear_selection=clear)
 def test_list_replacement_verifies_clear_then_adds(self):
  with patch.object(w.Atspi,'Selection',self.configure_list(),create=True):result=self.call()
  self.assertEqual(result['effect'],'verified');self.assertEqual(self.table.rows,{1,2,3});self.assertEqual(self.table.calls,[('clear',None),('add',1),('add',2),('add',3)]);self.assertEqual(self.receipt['progress']['verified_completed'],4)
 def test_list_failed_clear_never_adds_or_retries(self):
  with patch.object(w.Atspi,'Selection',self.configure_list(True),create=True):result=self.call()
  self.assertEqual(result['error'],'SELECTION_UNVERIFIABLE');self.assertEqual(result['effect'],'uncertain');self.assertEqual(self.table.calls,[('clear',None)]);self.assertEqual(self.table.rows,{0,5});self.assertEqual(self.receipt['progress']['verified_completed'],0);self.assertEqual(self.receipt['progress']['current_uncertain'],1)
 def test_selected_budget_refuses_before_normalization(self):
  self.table.rows=set(range(501));self.assertEqual(self.call()['error'],'SELECTION_TOO_LARGE');self.assertEqual(self.table.calls,[])

class SelectionProgressTests(unittest.TestCase):
 def test_strict_payload_free_receipt(self):
  from luda.progress import selection_progress,operation_progress
  good=dict(unit='selection_step',requested=4,verified_completed=1,current_uncertain=1,not_started=2,application_commit_verified=False)
  self.assertEqual(operation_progress(good),good)
  for bad in ({**good,'requested':True},{**good,'not_started':0},{**good,'text':'PRIVATE'},{**good,'application_commit_verified':True},{**good,'unit':'rich_text_segment'},{**good,'requested':551,'not_started':549}):
   self.assertIsNone(selection_progress(bad))
 def test_ax_accepts_receipt_only_for_range_and_never_foreign_units(self):
  import json
  from luda.desktop import Desktop
  from luda.common import DesktopError
  good=dict(unit='selection_step',requested=4,verified_completed=1,current_uncertain=1,not_started=2,application_commit_verified=False)
  desktop=object.__new__(Desktop)
  payload={'error':'STALE_TARGET','message':'Inspect again.','effect':'uncertain','progress':good}
  with patch('luda.desktop.run',return_value=json.dumps(payload).encode()):
   with self.assertRaises(DesktopError) as caught:desktop.ax({'op':'choose','range_end':{}},True)
   self.assertEqual(caught.exception.details['progress'],good)
   with self.assertRaises(DesktopError) as caught:desktop.ax({'op':'choose'},True)
   self.assertFalse(caught.exception.details)
  payload['progress']={**good,'unit':'key_chord'}
  with patch('luda.desktop.run',return_value=json.dumps(payload).encode()):
   with self.assertRaises(DesktopError) as caught:desktop.ax({'op':'choose','range_end':{}},True)
   self.assertFalse(caught.exception.details)

class RangeEndpointTests(unittest.TestCase):
 def test_only_same_inspection_and_window_is_dispatched(self):
  from luda.desktop import Desktop
  from luda.common import DesktopError
  from unittest.mock import Mock
  desktop=object.__new__(Desktop);desktop.target_window=Mock(return_value={'pid':1,'start':'start'});desktop.ax=Mock(return_value={'effect':'verified'})
  def entry(order,**extra):return dict(time=10,window_id='window',inspection_id='inspection',inspection_order=order,node={'start':'start','path':str(order)},**extra)
  desktop.elements={'a':entry(0),'b':entry(1),'c':entry(2)}
  with patch('luda.desktop.elapsed_time',return_value=11):
   desktop.element('c','choose',range_end_id='a',extend=False)
   request=desktop.ax.call_args.args[0];self.assertEqual([n['path'] for n in request['range_nodes']],['0','1','2'])
   for key,value in [('inspection_id','other'),('window_id','other'),('time',-100)]:
    original=desktop.elements['a'][key];desktop.elements['a'][key]=value;desktop.ax.reset_mock()
    with self.assertRaises(DesktopError) as caught:desktop.element('c','choose',range_end_id='a')
    self.assertEqual(caught.exception.code,'STALE_TARGET');desktop.ax.assert_not_called();desktop.elements['a'][key]=original
