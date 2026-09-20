import unittest
from unittest.mock import Mock, patch
from luda.desktop import Desktop
from luda.interaction import InteractionMixin


class PointerRouting(unittest.TestCase):
    def test_client_click_and_wheel_use_owned_supervisor(self):
        desktop=Desktop();self.addCleanup(desktop.close)
        desktop.point=Mock(return_value=(12,34))
        desktop.target_window=Mock(return_value={'xid':42})
        for kind,kwargs,button in [('click',{},'1'),('click',{'button':'right'},'3'),('scroll',{'direction':'left'},'6')]:
            with patch('luda.desktop.run') as run,patch('luda.desktop.click_button') as click:
                result=desktop.pointer('w','s',1,2,kind=kind,count=2,**kwargs)
                self.assertEqual(result['effect'],'dispatched')
                run.assert_called_once_with(['xdotool','mousemove','12','34'],effect='uncertain')
                click.assert_called_once_with(button,2,target=42)

    def test_popup_click_and_wheel_use_owner_focus(self):
        driver=Mock()
        driver._popup_point.return_value=(12,34)
        driver.target_window.return_value={'xid':42}
        for kind,button in [('click','1'),('scroll','5')]:
            with patch('luda.interaction.run') as run,patch('luda.interaction.click_button') as click:
                result=InteractionMixin.pointer_popup(driver,'w','p','s',1,2,kind=kind,count=2)
                self.assertEqual(result['effect'],'dispatched')
                run.assert_called_once_with(['xdotool','mousemove','12','34'],effect='uncertain')
                click.assert_called_once_with(button,2,target=42)
