import unittest
from unittest.mock import Mock, patch, call
from luda.desktop import Desktop
from luda.interaction import InteractionMixin
from luda.common import DesktopError


class PointerRouting(unittest.TestCase):
    def prepare(self, desktop, generation='generation'):
        desktop.private_input=Mock(environment=Mock(return_value={}))
        desktop.focus_input=Mock()
        desktop._interaction_point=Mock(return_value=(12,34))
        desktop.list_windows=Mock(return_value=[])
        desktop.signature=Mock(return_value=[])
        desktop.observe_popups=Mock(return_value=[])
        desktop.display=Mock(return_value=Mock(topology=Mock(return_value={'server_generation':generation})))
        desktop.snapshots['s']={'topology':{'server_generation':generation},'signature':[],'popups':[]}

    def test_restart_between_snapshot_check_and_preflight_cannot_rebind_click(self):
        desktop=Desktop();self.addCleanup(desktop.close)
        desktop.point=Mock(return_value=(12,34))
        desktop.target_window=Mock(return_value={'xid':42,'window_id':'observed:window-token'})
        self.prepare(desktop,'original')
        with patch('luda.interaction.check_pointer_ready',return_value={'server_generation':'replacement'}),patch('luda.desktop.click_button') as click:
            with self.assertRaises(DesktopError) as caught:desktop.pointer('w','s',1,2)
            self.assertEqual(caught.exception.code,'STALE_OBSERVATION')
            click.assert_not_called()

    def test_client_click_and_wheel_use_owned_supervisor(self):
        desktop=Desktop();self.addCleanup(desktop.close)
        desktop.point=Mock(return_value=(12,34))
        desktop.target_window=Mock(return_value={'xid':42,'window_id':'observed:window-token'})
        self.prepare(desktop)
        for kind,kwargs,button in [('click',{},'1'),('click',{'button':'right'},'3'),('scroll',{'direction':'left'},'6')]:
            with patch('luda.desktop.run') as run,patch('luda.desktop.click_button') as click,patch('luda.interaction.check_pointer_ready',return_value={'server_generation':'generation'}) as ready:
                result=desktop.pointer('w','s',1,2,kind=kind,count=2,**kwargs)
                self.assertEqual(result['effect'],'dispatched')
                run.assert_not_called()
                click.assert_called_once_with(button,2,target=42,position=(12,34),server_generation='generation',target_generation='window-token')
                ready.assert_has_calls([call(),call(42,target_generation='window-token')])
                self.assertEqual(ready.call_count,2)

    def test_popup_click_and_wheel_use_owner_focus(self):
        driver=Desktop();self.addCleanup(driver.close)
        driver._popup_point=Mock(return_value=(12,34))
        driver.target_window=Mock(return_value={'xid':42,'window_id':'observed:window-token'})
        self.prepare(driver)
        for kind,button in [('click','1'),('scroll','5')]:
            with patch('luda.interaction.run') as run,patch('luda.interaction.click_button') as click,patch('luda.interaction.check_pointer_ready',return_value={'server_generation':'generation'}) as ready:
                result=InteractionMixin.pointer_popup(driver,'w','p','s',1,2,kind=kind,count=2)
                self.assertEqual(result['effect'],'dispatched')
                run.assert_not_called()
                click.assert_called_once_with(button,2,target=42,position=(12,34),server_generation='generation',target_generation='window-token')
                ready.assert_has_calls([call(),call(42,target_generation='window-token')])
                self.assertEqual(ready.call_count,2)

    def test_held_input_refused_before_any_initial_movement(self):
        desktop=Desktop();self.addCleanup(desktop.close)
        desktop.point=Mock(return_value=(12,34))
        desktop._interaction_point=Mock(return_value=(12,34))
        desktop._popup_point=Mock(return_value=(12,34))
        desktop.target_window=Mock(return_value={'xid':42,'window_id':'observed:window-token'})
        self.prepare(desktop)
        calls=[lambda:desktop.pointer('w','s',1,2),
               lambda:desktop.pointer('w','s',1,2,kind='scroll'),
               lambda:desktop.pointer('w','s',1,2,kind='drag',end_x=4,end_y=5),
               lambda:desktop.hover('w','s',1,2),
               lambda:desktop.drag_between('w','other','s',1,2,4,5),
               lambda:desktop.pointer_popup('w','p','s',1,2),
               lambda:desktop.pointer_popup('w','p','s',1,2,kind='hover')]
        for call in calls:
            with patch('luda.interaction.check_pointer_ready',side_effect=DesktopError('INPUT_HELD','held')),patch('luda.desktop.run') as direct,patch('luda.interaction.run') as mixed:
                with self.assertRaises(DesktopError) as caught:call()
                self.assertEqual(caught.exception.code,'INPUT_HELD')
                direct.assert_not_called();mixed.assert_not_called()
