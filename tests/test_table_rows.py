import types
import unittest
from unittest.mock import patch
from test_semantic import load_worker
w=load_worker()
def rect(x=10,y=10,width=30,height=20):return types.SimpleNamespace(x=x,y=y,width=width,height=height)
class Cell:
 path='/row';name='Record 1';position=(True,1,0);app=types.SimpleNamespace(bus_name=':1.42')
 def get_role_name(self):return 'table cell'
 def get_table_cell(self):return self
 def get_table(self):return self.table
 def get_position(self):return self.position
 def get_name(self):return self.name
 def get_parent(self):return getattr(self,'parent',None)
 def get_index_in_parent(self):return getattr(self,'index',0)
 def get_child_at_index(self,index):return self.children[index] if index < len(self.children) else None
 def get_component_iface(self):return types.SimpleNamespace(get_extents=lambda _:self.bounds)
class Table:
 path='/table';app=types.SimpleNamespace(bus_name=':1.42')
 def __init__(self,cell):self.cell=cell;self.rows=set();self.calls=[];self.ignore=False;self.recycle=False;self.states={'sensitive','showing'}
 def get_interfaces(self):return ['Table','Component']
 def get_state_set(self):return types.SimpleNamespace(get_states=lambda:[types.SimpleNamespace(value_nick=s) for s in self.states])
 def get_component_iface(self):return types.SimpleNamespace(get_extents=lambda _:rect(0,0,100,100))
 def get_table_iface(self):return self
 def get_accessible_at(self,row,col):
  if row==1:return self.cell
  other=Cell();other.name='Record '+str(row);other.path='/row/'+str(row);return other
 def get_selected_rows(self):return list(self.rows)
 def add_row_selection(self,row):
  self.calls.append(('add',row))
  if not self.ignore:self.rows.add(row)
  if self.recycle:self.cell.name='Different record'
  return True
 def remove_row_selection(self,row):self.calls.append(('remove',row));self.rows.discard(row);return True
class Rows(unittest.TestCase):
 def setUp(self):
  self.cell=Cell();self.cell.bounds=rect();self.table=Table(self.cell);self.cell.table=self.table
  self.current={'role':'table cell','interfaces':['Component'],'name':'Record 1','name_fingerprint':w.bounded_name_identity(self.cell,False)[1]}
  self.patches=[patch.object(w.Atspi,'TableCell',Cell,create=True),patch.object(w.Atspi,'CoordType',types.SimpleNamespace(SCREEN=0),create=True),patch.object(w,'verify',lambda fn:fn())]
  for p in self.patches:p.start()
 def tearDown(self):
  for p in self.patches:p.stop()
 def call(self,extend=False):return w.choose_table_row(self.cell,self.current,extend)
 def composite(self):
  canonical=Cell();canonical.path='/canonical';canonical.name='';canonical.children=[self.cell]
  self.cell.parent=canonical;self.table.cell=canonical
  return canonical
 def test_stable_composite_renderer_selects_its_canonical_row(self):
  self.composite()
  result=self.call()
  self.assertEqual(result.get('effect'),'verified',result)
  self.assertEqual(self.table.rows,{1})
 def test_nested_composite_renderer_keeps_all_parent_links(self):
  canonical=self.composite();middle=Cell();middle.path='/middle';middle.children=[self.cell];middle.parent=canonical
  canonical.children=[middle];self.cell.parent=middle
  self.assertEqual(self.call()['effect'],'verified')
 def test_composite_wrong_parent_refuses_before_selection(self):
  self.composite();self.cell.parent=None
  self.assertEqual(self.call()['error'],'STALE_TARGET');self.assertEqual(self.table.calls,[])
 def test_composite_nonreciprocal_child_refuses_before_selection(self):
  canonical=self.composite();replacement=Cell();replacement.path='/other';canonical.children=[replacement]
  self.assertEqual(self.call()['error'],'STALE_TARGET');self.assertEqual(self.table.calls,[])
 def test_composite_cyclic_ancestry_refuses_before_selection(self):
  self.composite();self.cell.parent=self.cell;self.cell.children=[self.cell]
  self.assertEqual(self.call()['error'],'STALE_TARGET');self.assertEqual(self.table.calls,[])
 def test_composite_replaced_canonical_before_mutation_refused(self):
  self.composite();original=self.table.get_selected_rows
  def rows():
   replacement=Cell();replacement.path='/replacement';replacement.name='';self.table.cell=replacement
   return original()
  self.table.get_selected_rows=rows
  self.assertEqual(self.call()['error'],'STALE_TARGET');self.assertEqual(self.table.calls,[])
 def test_composite_changed_ancestry_before_mutation_refused(self):
  canonical=self.composite();original=self.table.get_selected_rows
  def rows():
   middle=Cell();middle.path='/new-middle';middle.children=[self.cell];middle.parent=canonical
   self.cell.parent=middle;canonical.children=[middle]
   return original()
  self.table.get_selected_rows=rows
  self.assertEqual(self.call()['error'],'STALE_TARGET');self.assertEqual(self.table.calls,[])
 def test_composite_mutations_after_selection_are_uncertain(self):
  for mutation in ('canonical','parent','index','position','owner','label','canonical-label'):
   with self.subTest(mutation=mutation):
    self.setUp_composite_mutation(mutation)
 def setUp_composite_mutation(self,mutation):
  self.cell=Cell();self.cell.bounds=rect();self.table=Table(self.cell);self.cell.table=self.table
  canonical=self.composite();original=self.table.add_row_selection
  def add(row):
   result=original(row)
   if mutation=='canonical':
    replacement=Cell();replacement.path='/replacement';replacement.name='';self.table.cell=replacement
   elif mutation=='parent':self.cell.parent=None
   elif mutation=='index':self.cell.index=1
   elif mutation=='position':self.cell.position=(True,2,0)
   elif mutation=='owner':self.cell.table=Table(self.cell);self.cell.table.path='/other-table'
   elif mutation=='label':self.cell.name='Different record'
   elif mutation=='canonical-label':canonical.name='Different meaning'
   return result
  self.table.add_row_selection=add
  result=self.call();self.assertEqual(result['effect'],'uncertain');self.assertFalse(result['selected'])
 def test_inspected_composite_snapshot_roundtrips_json(self):
  import json
  canonical=self.composite()
  observed=json.loads(json.dumps(w.table_cell_observation(self.cell)))
  result=w.choose_table_row(self.cell,self.current,False,{'target':{'table_cell':observed,'parent_path':canonical.path}})
  self.assertEqual(result['effect'],'verified')
 def test_reparented_since_inspection_refused_before_selection(self):
  canonical=self.composite();observed=w.table_cell_observation(self.cell)
  replacement=Cell();replacement.path='/new-parent';replacement.name='';replacement.children=[self.cell]
  self.cell.parent=replacement;self.table.cell=replacement
  result=w.choose_table_row(self.cell,self.current,False,{'target':{'table_cell':observed,'parent_path':canonical.path}})
  self.assertEqual(result['error'],'STALE_TARGET');self.assertEqual(self.table.calls,[])
 def test_row_reordered_since_inspection_refused_before_selection(self):
  canonical=self.composite();observed=w.table_cell_observation(self.cell)
  self.cell.position=(True,2,0);self.table.get_accessible_at=lambda row,column:canonical
  result=w.choose_table_row(self.cell,self.current,False,{'target':{'table_cell':observed}})
  self.assertEqual(result['error'],'STALE_TARGET');self.assertEqual(self.table.calls,[])
 def test_replaced_canonical_with_same_parent_path_since_inspection_refused(self):
  canonical=self.composite();observed=w.table_cell_observation(self.cell)
  canonical.app=types.SimpleNamespace(bus_name=':1.99')
  result=w.choose_table_row(self.cell,self.current,False,{'target':{'table_cell':observed}})
  self.assertEqual(result['error'],'STALE_TARGET');self.assertEqual(self.table.calls,[])
 def test_unavailable_inspection_snapshot_refuses_before_selection(self):
  self.composite()
  result=w.choose_table_row(self.cell,self.current,False,{'target':{'table_cell':None}})
  self.assertEqual(result['error'],'STALE_TARGET');self.assertEqual(self.table.calls,[])
 def test_exact_row_and_single_selection_normalization(self):
  self.table.rows={2,3};r=self.call();self.assertEqual(r['effect'],'verified');self.assertEqual(self.table.rows,{1})
 def test_extend_preserves_other_rows(self):
  self.table.rows={2};self.assertEqual(self.call(True)['effect'],'verified');self.assertEqual(self.table.rows,{1,2})
 def test_offscreen_sentinel_refused_before_mutation(self):
  self.cell.bounds=rect(-2147483648,-2147483648);self.assertEqual(self.call()['error'],'NOT_INTERACTABLE');self.assertEqual(self.table.calls,[])
 def test_ignored_provider_acceptance_not_verified(self):
  self.table.ignore=True;self.assertEqual(self.call()['effect'],'uncertain')
 def test_recycled_cell_meaning_after_selection_not_verified(self):
  self.table.recycle=True;self.assertEqual(self.call()['effect'],'uncertain')
 def test_position_changed_before_action_refused(self):
  self.cell.position=(True,-1,0);self.assertEqual(self.call()['error'],'STALE_TARGET');self.assertEqual(self.table.calls,[])
 def test_disabled_or_hidden_table_refused_before_selection(self):
  for states in ({'showing'},{'sensitive'},set()):
   self.table.states=states;self.assertEqual(self.call()['error'],'NOT_INTERACTABLE')
  self.assertEqual(self.table.calls,[])
 def test_unreliable_coordinates_refuse_viewport_claim(self):
  result=w.choose_table_row(self.cell,self.current,False,{'target':{'bounds_coordinates':'unavailable'}})
  self.assertEqual(result['error'],'UNSUPPORTED');self.assertEqual(self.table.calls,[])
 def test_name_budget_failure_after_selection_retains_uncertainty(self):
  original=self.table.add_row_selection
  def add(row):
   result=original(row);self.cell.name='x'*1_048_577;return result
  self.table.add_row_selection=add
  with patch.object(w,'main',side_effect=lambda req:w.choose_table_row(self.cell,self.current,False,request=req)):
   result=w.dispatch({'op':'choose'})
  self.assertEqual(result['error'],'TARGET_IDENTITY_UNAVAILABLE');self.assertEqual(result['effect'],'uncertain')
 def test_actual_replacement_cell_name_not_verified(self):
  original=self.table.add_row_selection
  def add(row):
   result=original(row);replacement=Cell();replacement.name='Replacement';self.table.cell=replacement;return result
  self.table.add_row_selection=add
  self.assertEqual(self.call()['effect'],'uncertain')
 def test_actual_replacement_provider_not_verified(self):
  original=self.table.add_row_selection
  def add(row):
   result=original(row);replacement=Cell();replacement.app=types.SimpleNamespace(bus_name=':1.99');self.table.cell=replacement;return result
  self.table.add_row_selection=add
  self.assertEqual(self.call()['effect'],'uncertain')
 def test_extend_reordered_prior_row_not_verified(self):
  self.table.rows={2};original=self.table.get_accessible_at;changed=[False]
  def cell(row,column):
   value=original(row,column)
   if row==2 and changed[0]:value.name='Replacement prior row'
   return value
  self.table.get_accessible_at=cell
  add=self.table.add_row_selection
  def select(row):
   result=add(row);changed[0]=True;return result
  self.table.add_row_selection=select
  self.assertEqual(self.call(True)['effect'],'uncertain')
 def test_missing_prior_row_anchor_refuses_before_mutation(self):
  self.table.rows={2};original=self.table.get_accessible_at
  self.table.get_accessible_at=lambda row,column:None if row==2 else original(row,column)
  self.assertEqual(self.call(True)['error'],'SELECTION_UNVERIFIABLE');self.assertEqual(self.table.calls,[])
if __name__=='__main__':unittest.main()
