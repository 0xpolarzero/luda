import unittest
from unittest.mock import Mock,patch
from luda.common import DesktopError
from luda.interaction import InteractionMixin
from luda.x11 import X11

class Driver(InteractionMixin):
    def __init__(self):
        self.windows={'owner':{'window_id':'owner','xid':10,'pid':100,'workspace':0,'bounds':{'x':0,'y':0,'width':100,'height':100},'frame_bounds':{'x':0,'y':0,'width':100,'height':100}}}
        self.native=Mock(root=1);self.native.root_surface.side_effect=lambda xid:xid*10
        self.native.children.return_value=[100,200]
    def target_window(self,*args):return self.windows['owner']
    def list_windows(self):return list(self.windows.values())
    def display(self):return self.native
    def active(self):return 20
    def _await_state(self,predicate,extra):return {'effect':'verified' if predicate() else 'dispatched',**extra}

class WindowStateTests(unittest.TestCase):
    @patch('luda.interaction.run')
    @patch('luda.interaction.properties',return_value='_NET_WM_STATE_FULLSCREEN')
    def test_fullscreen_verified_by_exact_ewmh_flag(self,properties,run):
        result=Driver().manage_window('owner','fullscreen')
        self.assertEqual(result['effect'],'verified')
        run.assert_called_once_with(['wmctrl','-ir','10','-b','add,fullscreen'],effect='uncertain')
    @patch('luda.interaction.run')
    @patch('luda.interaction.properties',return_value='')
    def test_restore_removes_fullscreen_and_maximization(self,properties,run):
        result=Driver().manage_window('owner','restore')
        self.assertEqual(result['effect'],'verified')
        self.assertEqual([call.args[0] for call in run.call_args_list],[['wmctrl','-ir','10','-b','remove,maximized_vert,maximized_horz'],['wmctrl','-ir','10','-b','remove,fullscreen']])
    @patch('luda.interaction.run')
    @patch('luda.interaction.properties', side_effect=['_NET_WM_STATE_HIDDEN', '', ''])
    def test_minimized_restore_uses_no_initial_focus_request(self, properties, run):
        driver = Driver()
        driver.manage_window('owner', 'restore')
        driver.native.map_without_focus.assert_called_once_with(10, 'owner')
        self.assertFalse(any('windowmap' in call.args[0] for call in run.call_args_list))
    @patch('luda.interaction.run')
    def test_no_extra_arguments_for_new_actions(self,run):
        for action in ('raise','fullscreen'):
            with self.subTest(action=action),self.assertRaises(DesktopError):Driver().manage_window('owner',action,x=1)
        run.assert_not_called()
    @patch('luda.interaction.run',return_value=b'_NET_WM_STATE_HIDDEN')
    def test_hidden_raise_refused_without_input(self,run):
        driver=Driver()
        with self.assertRaises(DesktopError) as exc:driver.manage_window('owner','raise')
        self.assertEqual(exc.exception.code,'NOT_INTERACTABLE');driver.native.restack_above.assert_not_called()
    @patch('luda.interaction.run',return_value=b'')
    def test_raise_uses_explicit_peer_and_detects_focus_change(self,run):
        driver=Driver();driver.windows['peer']={'window_id':'peer','xid':20,'pid':200,'workspace':0}
        driver.active=Mock(side_effect=[20,10])
        with self.assertRaises(DesktopError) as exc:driver.manage_window('owner','raise')
        self.assertEqual(exc.exception.code,'FOCUS_CHANGED');self.assertEqual(exc.exception.effect,'uncertain')
        driver.native.restack_above.assert_called_once_with(10,20)
        self.assertTrue(all(call.args[0][0]=='xprop' for call in run.call_args_list))
    @patch('luda.interaction.run',return_value=b'')
    def test_already_raised_window_sends_no_restack(self,run):
        driver=Driver();driver.native.children.return_value=[100]
        self.assertEqual(driver.manage_window('owner','raise')['effect'],'verified')
        driver.native.restack_above.assert_not_called()
    @patch('luda.interaction.run',return_value=b'')
    def test_sticky_raise_includes_active_workspace_peers(self,run):
        driver=Driver();driver.windows['owner']['workspace']=-1
        driver.windows['peer']={'window_id':'peer','xid':20,'pid':200,'workspace':2}
        driver.workspaces=lambda:[{'workspace':2,'active':True}]
        driver.manage_window('owner','raise')
        driver.native.restack_above.assert_called_once_with(10,20)
    @patch('luda.interaction.run')
    @patch('luda.interaction.properties',return_value='_NET_WM_STATE_MODAL')
    def test_close_modal_is_dispatched_and_never_confirmed(self,properties,run):
        driver=Driver();driver.windows['dialog']={'window_id':'dialog','xid':30,'pid':100,'workspace':0};driver.native.transient_for.return_value=10
        result=driver.manage_window('owner','close')
        self.assertEqual(result['effect'],'dispatched');self.assertEqual(result['outcome'],'blocked_by_dialog');self.assertEqual(result['dialog_window_ids'],['dialog'])
        run.assert_called_once_with(['wmctrl','-ic','10'],effect='uncertain')
    @patch('luda.x11.run',return_value=b'{"result":1}')
    def test_native_restack_rejects_ambiguous_target(self,run):
        x=X11();run.reset_mock()
        for target,peer in ((1,1),(1,None),(True,2),(1,0)):
            with self.subTest(target=target,peer=peer),self.assertRaises(DesktopError):x.restack_above(target,peer)
        run.assert_not_called()

if __name__=='__main__':unittest.main()
