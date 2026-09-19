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
    @patch('luda.interaction.time.sleep')
    @patch('luda.interaction.run')
    def test_drag_releases_after_motion_failure(self, run, sleep):
        run.side_effect = [b'',b'',DesktopError('TIMEOUT','test'),b'']
        with self.assertRaises(DesktopError): Dummy().drag_between('a','b','s',1,2,3,4)
        self.assertEqual(run.call_args.args[0],['xdotool','mouseup','1'])
        self.assertTrue(run.call_args.kwargs['cleanup'])
    @patch('luda.interaction.run')
    def test_destination_validated_before_input(self, run):
        d=Dummy()
        d._interaction_point = lambda window,*args: (_ for _ in ()).throw(DesktopError('OUT_OF_BOUNDS','test')) if window == 'b' else (1,2)
        with self.assertRaises(DesktopError): d.drag_between('a','b','s',1,2,3,4)
        run.assert_not_called()
    @patch('luda.interaction.run',return_value=b'0  * DG: 1440x900 VP: 0,0 WA: 0,30 1440x870 Main workspace\n1  - DG: 1440x900 VP: N/A WA: 0,30 1440x870 Second\n')
    def test_workspace_names(self, run):
        self.assertEqual(Dummy().workspaces(),[{'workspace':0,'active':True,'name':'Main workspace'},{'workspace':1,'active':False,'name':'Second'}])

if __name__ == '__main__': unittest.main()
