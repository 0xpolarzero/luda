import tempfile
import base64
import io
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
from PIL import Image
from luda.common import DesktopError
from luda.desktop import Desktop

class ScreenshotLimitsTests(unittest.TestCase):
    def driver(self,width,height):
        d=Desktop();self.addCleanup(d.close)
        d.x=Mock();d.x.root=1;d.x.geometry.return_value={'width':width,'height':height}
        d.x.topology.return_value={'root':d.x.geometry.return_value,'randr':{'version':[1,6],'monitors':[],'crtcs':[]}}
        d.list_windows=Mock(return_value=[]);d.observe_popups=Mock(return_value=[])
        return d
    def test_oversized_native_capture_refused_before_capture(self):
        for width,height in ((8000,8000),(0,100),(-1,100)):
            d=self.driver(width,height)
            with patch('luda.desktop.run') as run,self.assertRaises(DesktopError) as caught:d.observe()
            self.assertEqual(caught.exception.code,'SCREENSHOT_LIMIT');run.assert_not_called()
    def test_tall_screenshot_bounded_and_aspect_ratio_preserved(self):
        d=self.driver(90,9000)
        def capture(args,**kwargs):Image.new('RGB',(90,9000)).save(args[-1])
        with patch('luda.desktop.run',side_effect=capture):result=d.observe()
        self.assertEqual(result['image_size'],{'width':26,'height':2560})
        self.assertEqual(result['desktop_size'],{'width':90,'height':9000})
    def test_resolution_changed_during_capture_returns_no_snapshot(self):
        d=self.driver(100,100)
        def capture(args,**kwargs):Image.new('RGB',(101,100)).save(args[-1])
        with patch('luda.desktop.run',side_effect=capture),self.assertRaises(DesktopError) as caught:d.observe()
        self.assertEqual(caught.exception.code,'DESKTOP_CHANGED');self.assertFalse(d.snapshots)

    def test_valid_black_frame_remains_real_black_image(self):
        d=self.driver(100,100)
        def capture(args,**kwargs):Image.new('RGB',(100,100),(0,0,0)).save(args[-1])
        with patch('luda.desktop.run',side_effect=capture):result=d.observe()
        with Image.open(io.BytesIO(base64.b64decode(result['image_base64']))) as actual:
            self.assertEqual(actual.getextrema(),((0,0),(0,0),(0,0)))
        self.assertIn(result['snapshot_id'],d.snapshots)

    def test_missing_or_corrupt_capture_never_becomes_synthetic_black_frame(self):
        buffer=io.BytesIO();Image.new('RGB',(100,100),'white').save(buffer,format='PNG')
        for payload in (b'',b'not an image',buffer.getvalue()[:50]):
            d=self.driver(100,100)
            def capture(args,**kwargs):Path(args[-1]).write_bytes(payload)
            with patch('luda.desktop.run',side_effect=capture),self.assertRaises(DesktopError) as caught:d.observe()
            self.assertEqual(caught.exception.code,'SCREENSHOT_UNAVAILABLE')
            self.assertEqual(caught.exception.effect,'none')
            self.assertFalse(d.snapshots)

if __name__=='__main__':unittest.main()
