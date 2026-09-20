import unittest
from luda.window_history import WindowHistory
NORMAL='_NET_WM_STATE = \nWM_NORMAL_HINTS: minimum 300 by 180'
MAX='_NET_WM_STATE = _NET_WM_STATE_MAXIMIZED_VERT, _NET_WM_STATE_MAXIMIZED_HORZ\nWM_NORMAL_HINTS: minimum 300 by 180'
def window(width=400,identity='one'):
 return {'window_id':identity,'workspace':0,'bounds':dict(x=10,y=30,width=width,height=300),'frame_bounds':dict(x=8,y=8,width=width+4,height=324)}
class HistoryTests(unittest.TestCase):
 def setUp(self):self.history=WindowHistory();self.history.capture('one',window(),NORMAL,window(1000),MAX)
 def context(self,state=MAX,current=None):return self.history.context(current or window(1000),state,self.history.take('one'))
 def test_matched_and_nonmatching_are_historical_only(self):
  record=self.context()
  self.assertEqual(self.history.compare(record,window(),NORMAL)['status'],'matched')
  self.assertEqual(self.history.compare(record,window(500),NORMAL)['status'],'nonmatching')
  self.assertNotIn('effect',self.history.compare(record,window(),NORMAL))
 def test_current_external_state_or_hints_change_unknown(self):
  for state in (NORMAL,MAX.replace('300 by 180','500 by 180')):
   with self.subTest(state=state):
    self.setUp();record=self.context(state);self.assertEqual(record['reason'],'state_geometry_or_hints_changed')
 def test_observed_external_change_and_revert_stays_unknown(self):
  self.history.observe([window(800)]);self.history.observe([window(1000)])
  self.assertEqual(self.context()['reason'],'observed_geometry_changed')
 def test_replacement_never_inherits_reference(self):
  self.history.observe([window(1000,'replacement')])
  self.assertEqual(self.history.entries,{})
  self.assertEqual(self.history.compare(self.history.take('replacement'),window(),NORMAL)['reason'],'no_prior_maximize')
 def test_own_other_action_invalidates_even_matching_final_geometry(self):
  self.history.invalidate('one');self.history.observe([window(1000)])
  self.assertEqual(self.context()['reason'],'another_window_action')
 def test_repeated_maximize_keeps_original_reference(self):
  before=self.context();self.history.put('one',self.history.context(window(1000),MAX,before))
  self.assertEqual(self.history.compare(self.context(),window(),NORMAL)['status'],'matched')
 def test_postrestore_hints_change_is_unknown_not_guessed_constraint(self):
  result=self.history.compare(self.context(),window(),NORMAL.replace('300','500'))
  self.assertEqual(result['status'],'unknown');self.assertNotIn('constraint_reason',result)
 def test_unstable_capture_or_missing_hints_never_known(self):
  for before,stable in [(NORMAL,False),('',True)]:
   self.history.capture('one',window(),before,window(1000),MAX,stable)
   self.assertEqual(self.history.entries['one']['reason'],'maximize_reference_unavailable')
 def test_resource_bound_and_clear(self):
  for i in range(70):self.history.put(str(i),{'reason':'test'})
  self.assertEqual(len(self.history.entries),64);self.assertNotIn('0',self.history.entries)
  self.history.clear();self.assertFalse(self.history.entries)

if __name__=='__main__':unittest.main()
