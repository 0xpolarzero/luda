import types
import unittest
from unittest.mock import patch
from test_semantic import load_worker
w=load_worker()
def rect(x=10,y=10,width=30,height=20):return types.SimpleNamespace(x=x,y=y,width=width,height=height)
class Cell:
 path='/row';name='Record 1';position=(True,1,0)
 def get_table_cell(self):return self
 def get_table(self):return self.table
 def get_position(self):return self.position
 def get_name(self):return self.name
 def get_component_iface(self):return types.SimpleNamespace(get_extents=lambda _:self.bounds)
class Table:
 path='/table'
 def __init__(self,cell):self.cell=cell;self.rows=set();self.calls=[];self.ignore=False;self.recycle=False
 def get_interfaces(self):return ['Table','Component']
 def get_component_iface(self):return types.SimpleNamespace(get_extents=lambda _:rect(0,0,100,100))
 def get_table_iface(self):return self
 def get_accessible_at(self,row,col):return self.cell
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
  self.current={'interfaces':['Component'],'name':'Record 1'}
  self.patches=[patch.object(w.Atspi,'TableCell',Cell,create=True),patch.object(w.Atspi,'CoordType',types.SimpleNamespace(SCREEN=0),create=True),patch.object(w,'verify',lambda fn:fn())]
  for p in self.patches:p.start()
 def tearDown(self):
  for p in self.patches:p.stop()
 def call(self,extend=False):return w.choose_table_row(self.cell,self.current,extend)
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
if __name__=='__main__':unittest.main()
