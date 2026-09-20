import unittest
from unittest.mock import patch
from luda.interaction import InteractionMixin, integer
from luda.common import DesktopError

class Dummy(InteractionMixin):
    def target_window(self,*args): return {'xid':42}
    def _interaction_point(self, window,*args): return (10,20) if window == 'a' else (40,50)
    def list_windows(self): return []

class InteractionTests(unittest.TestCase):
    def test_integer_rejects_bool_float_nan(self):
        for value in (True,1.0,float('nan'),None,-1,5):
            with self.subTest(value=value), self.assertRaises(DesktopError): integer(value,'n',0,4)
    @patch('luda.interaction.run')
    def test_invalid_arguments_have_no_effect(self, run):
        for action, kwargs in [('move',{'x':1}),('resize',{'width':0,'height':5}),('close',{'x':3}),('wat',{}),('move',{'x':True,'y':3})]:
            with self.subTest(action=action), self.assertRaises(DesktopError): Dummy().manage_window('a',action,**kwargs)
        run.assert_not_called()
    @patch('luda.interaction.run')
    def test_close_verifies_disappearance(self, run):
        self.assertEqual(Dummy().manage_window('a','close')['effect'],'verified')
        run.assert_called_once_with(['wmctrl','-ic','42'],effect='uncertain')
    @patch('luda.interaction.held_button')
    @patch('luda.interaction.time.sleep')
    @patch('luda.interaction.run')
    def test_drag_guard_exits_after_motion_failure(self, run, sleep, guard):
        run.side_effect = [b'',DesktopError('TIMEOUT','test')]
        with self.assertRaises(DesktopError): Dummy().drag_between('a','b','s',1,2,3,4)
        guard.assert_called_once_with('1')
        self.assertIs(guard.return_value.__exit__.call_args.args[0],DesktopError)
    @patch('luda.interaction.run')
    def test_destination_validated_before_input(self, run):
        d=Dummy()
        d._interaction_point = lambda window,*args: (_ for _ in ()).throw(DesktopError('OUT_OF_BOUNDS','test')) if window == 'b' else (1,2)
        with self.assertRaises(DesktopError): d.drag_between('a','b','s',1,2,3,4)
        run.assert_not_called()
    @patch('luda.interaction.run',return_value=b'0  * DG: 1440x900 VP: 0,0 WA: 0,30 1440x870 Main workspace\n1  - DG: 1440x900 VP: N/A WA: 0,30 1440x870 Second\n')
    def test_workspace_names(self, run):
        self.assertEqual(Dummy().workspaces(),[{'workspace':0,'active':True,'name':'Main workspace'},{'workspace':1,'active':False,'name':'Second'}])


class MoreInteractionTests(unittest.TestCase):
    @patch('luda.interaction.held_button')
    @patch('luda.interaction.run')
    def test_guard_failure_retains_code_and_prevents_drag_motion(self, run, guard):
        guard.return_value.__enter__.side_effect=DesktopError('INPUT_GUARD_UNAVAILABLE','test')
        with self.assertRaises(DesktopError) as caught: Dummy().drag_between('a','b','s',1,2,3,4)
        self.assertEqual(caught.exception.code,'INPUT_GUARD_UNAVAILABLE')
        run.assert_called_once_with(['xdotool','mousemove','10','20'],effect='uncertain')
    @patch('luda.interaction.run')
    def test_invalid_pointer_button_has_no_effect(self, run):
        with self.assertRaises(DesktopError): Dummy().drag_between('a','b','s',1,2,3,4,button='invalid')
        run.assert_not_called()
    def test_nonfinite_pointer_coordinates(self):
        for v in (None, True, float('inf'),float('nan'),'5'):
            with self.subTest(value=v),self.assertRaises(DesktopError): InteractionMixin._interaction_point(Dummy(),'a','s',v,4)
    @patch('luda.interaction.time.sleep')
    @patch('luda.interaction.time.monotonic',side_effect=[0,0,2])
    def test_unobserved_effect_not_reported_verified(self, monotonic, sleep):
        self.assertEqual(Dummy()._await_state(lambda:False,{'action':'close'})['effect'],'dispatched')

class PointTests(unittest.TestCase):
    def driver(self):
        import time
        d=Dummy();d.windows={'a':{'xid':10,'bounds':{'x':10,'y':10,'width':40,'height':30}}}
        d.snapshots={'s':{'time':time.monotonic(),'native':(100,100),'image':(50,50),'signature':'same'}}
        d.target_window=lambda *args: d.windows['a']
        d.signature=lambda windows:'same'
        class Display:
            root=1
            def topology(self): return {'generation': 1}
            def surface_at(self,x,y):return 20
            def root_surface(self,xid):return 20
            def geometry(self, root): return {'width':100,'height':100}
        d.display=lambda:Display()
        d.snapshots['s']['topology'] = d.display().topology()
        return d
    def test_scales_image_to_root_and_rejects_half_open_edges(self):
        d=self.driver()
        self.assertEqual(InteractionMixin._interaction_point(d,'a','s',5,5),(10,10))
        self.assertEqual(InteractionMixin._interaction_point(d,'a','s',24.9,19.9),(49,39))
        for x,y in [(25,10),(10,20),(-1,10),(50,10),(10,50),(4,10)]:
            with self.subTest(x=x,y=y), self.assertRaises(DesktopError): InteractionMixin._interaction_point(d,'a','s',x,y)
    def test_expired_missing_and_changed_layout_rejected(self):
        d=self.driver()
        for token in ('missing',None):
            with self.assertRaises(DesktopError): InteractionMixin._interaction_point(d,'a',token,5,5)
        d.snapshots['s']['time']-=16
        with self.assertRaises(DesktopError): InteractionMixin._interaction_point(d,'a','s',5,5)
        d=self.driver();d.signature=lambda windows:'changed'
        with self.assertRaises(DesktopError): InteractionMixin._interaction_point(d,'a','s',5,5)
    def test_covered_client_refused_before_pointer_input(self):
        d=self.driver()
        display=d.display()
        display.surface_at=lambda x,y:99
        d.display=lambda:display
        with self.assertRaises(DesktopError) as caught:
            InteractionMixin._interaction_point(d,'a','s',5,5)
        self.assertEqual(caught.exception.code,'OCCLUDED_TARGET')

    def test_changed_resolution_rejected(self):
        d=self.driver();d.snapshots['s']['native']=(200,100)
        with self.assertRaises(DesktopError): InteractionMixin._interaction_point(d,'a','s',5,5)

if __name__ == "__main__": unittest.main()
