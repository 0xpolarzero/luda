import copy
import time
import unittest
from unittest.mock import patch
from luda.common import DesktopError
from luda.interaction import InteractionMixin

OWNER={'xid':10,'pid':100,'start':'123','window_id':'owner','bounds':{'x':0,'y':0,'width':40,'height':40}}
POPUP={'xid':20,'pid':100,'transient_for':10,'override_redirect':True,'bounds':{'x':50,'y':50,'width':40,'height':30}}

class Display:
    root=1
    def __init__(self,popups):self.popups=popups;self.top=20
    def popup_surfaces(self):return self.popups
    def window_tokens(self,xids):return {xid: str(xid) for xid in xids}
    def geometry(self,xid):return {'width':100,'height':100}
    def surface_at(self,x,y):return self.top

class Driver(InteractionMixin):
    def __init__(self,popups=None):
        self.x=Display(copy.deepcopy([POPUP] if popups is None else popups));self.windows={'owner':copy.deepcopy(OWNER)}
        self.snapshots={}
    def display(self):return self.x
    def list_windows(self):return list(self.windows.values())
    def target_window(self,*args):return self.windows['owner']
    def signature(self,windows):return 'layout'
    def capture(self):
        popups=self.observe_popups()
        self.snapshots['s']={'time':time.monotonic(),'popups':popups,'signature':'layout','native':(100,100),'image':(100,100)}
        return popups[0]['popup_id']

@patch('luda.interaction.process_identity',return_value='123')
class PopupTests(unittest.TestCase):
    def test_owner_chain_matches_pid_and_process_start(self,identity):
        d=Driver([POPUP,{**POPUP,'xid':30,'transient_for':20}])
        result=d.observe_popups()
        self.assertEqual([p['owner_window_id'] for p in result],['owner','owner'])
        self.assertNotEqual(result[0]['popup_id'],result[1]['popup_id'])
    def test_ambiguous_unowned_cross_process_and_cycle_rejected(self,identity):
        for popup in ({**POPUP,'transient_for':None},{**POPUP,'pid':101},{**POPUP,'transient_for':20}):
            with self.subTest(popup=popup):self.assertEqual(Driver([popup]).observe_popups(),[])
    def test_reused_owner_process_rejected(self,identity):
        identity.return_value='124'
        self.assertEqual(Driver().observe_popups(),[])
    def test_dead_process_rejected(self,identity):
        identity.side_effect=DesktopError('STALE_TARGET','gone')
        self.assertEqual(Driver().observe_popups(),[])
    def test_target_outside_owner_inside_popup_is_valid(self,identity):
        d=Driver();token=d.capture()
        self.assertEqual(d._popup_point('owner',token,'s',60,60),(60,60))
    def test_forged_or_wrong_owner_token_rejected(self,identity):
        d=Driver();token=d.capture()
        for owner,popup in [('owner','20'),('other',token)]:
            with self.subTest(owner=owner),self.assertRaises(DesktopError) as e:d._popup_point(owner,popup,'s',60,60)
            self.assertEqual(e.exception.code,'STALE_TARGET')
    def test_vanished_moved_or_new_popup_rejected(self,identity):
        for change in ('vanish','move','new','reuse'):
            d=Driver();token=d.capture()
            if change=='vanish':d.x.popups=[]
            elif change=='move':d.x.popups[0]['bounds']['x']+=1
            elif change=='reuse':d.x.window_tokens=lambda xids: {xid:'new' for xid in xids}
            else:d.x.popups.append({**POPUP,'xid':30})
            with self.subTest(change=change),self.assertRaises(DesktopError) as e:d._popup_point('owner',token,'s',60,60)
            self.assertEqual(e.exception.code,'STALE_OBSERVATION')
    @patch('luda.interaction.run')
    def test_overlap_rejected_before_mousemove(self,run,identity):
        d=Driver();token=d.capture();d.x.top=99
        with self.assertRaises(DesktopError) as e:d.pointer_popup('owner',token,'s',60,60)
        self.assertEqual(e.exception.code,'OCCLUDED_TARGET');run.assert_not_called()
    @patch('luda.interaction.run')
    def test_invalid_kind_count_button_and_direction_have_no_effect(self,run,identity):
        d=Driver();token=d.capture()
        for kwargs in ({'kind':'drag'},{'count':True},{'button':'bad'},{'direction':'bad'}):
            with self.subTest(kwargs=kwargs),self.assertRaises(DesktopError):d.pointer_popup('owner',token,'s',60,60,**kwargs)
        run.assert_not_called()
    def test_nonfinite_or_edge_coordinates_rejected(self,identity):
        d=Driver();token=d.capture()
        for x,y in [(float('nan'),60),(True,60),(90,60),(60,80),(100,60),(-1,60)]:
            with self.subTest(x=x,y=y),self.assertRaises(DesktopError):d._popup_point('owner',token,'s',x,y)
    def test_snapshot_expiry_rejected(self,identity):
        d=Driver();token=d.capture();d.snapshots['s']['time']-=16
        with self.assertRaises(DesktopError) as e:d._popup_point('owner',token,'s',60,60)
        self.assertEqual(e.exception.code,'STALE_OBSERVATION')

if __name__=='__main__':unittest.main()
