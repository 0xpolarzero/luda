import ctypes as C
import unittest
from unittest.mock import patch
from PIL import Image
from luda._randr import bounded_values
from luda.common import DesktopError
from luda.interaction import InteractionMixin
from tests import test_interaction, test_screenshot_limits
from tests.test_popups import Driver


class TopologyTests(unittest.TestCase):
    def test_same_size_layout_change_refuses_client_pointer(self):
        driver=test_interaction.PointTests().driver()
        display=driver.display();display.topology=lambda: {'generation': 2}
        driver.display=lambda: display
        with self.assertRaises(DesktopError) as caught:InteractionMixin._interaction_point(driver,'a','s',10,10)
        self.assertEqual(caught.exception.code,'STALE_OBSERVATION')

    @patch('luda.interaction.process_identity',return_value='123')
    def test_same_size_layout_change_refuses_popup_pointer(self,identity):
        driver=Driver();popup=driver.capture()
        driver.x.topology=lambda: {'generation': 2}
        with self.assertRaises(DesktopError) as caught:driver._popup_point('owner',popup,'s',55,55)
        self.assertEqual(caught.exception.code,'STALE_OBSERVATION')

    def test_layout_change_during_capture_returns_no_snapshot(self):
        fixture=test_screenshot_limits.ScreenshotLimitsTests();driver=fixture.driver(100,100)
        try:
            driver.x.topology.side_effect=[{'generation':1},{'generation':2}]
            def capture(args,**kwargs):Image.new('RGB',(100,100)).save(args[-1])
            with patch('luda.desktop.run',side_effect=capture),self.assertRaises(DesktopError) as caught:driver.observe()
            self.assertEqual(caught.exception.code,'DESKTOP_CHANGED')
            self.assertFalse(driver.snapshots)
        finally:fixture.doCleanups()

    def test_native_array_bounds_and_missing_pointer_fail_closed(self):
        for count in (-1,65,2**30,1):
            with self.assertRaises(DesktopError):bounded_values(C.POINTER(C.c_ulong)(),count)
        self.assertEqual(bounded_values(C.POINTER(C.c_ulong)(),0),[])
        self.assertEqual(bounded_values((C.c_ulong*2)(9,7),2),[9,7])
