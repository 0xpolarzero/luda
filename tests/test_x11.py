import json
import unittest
from unittest.mock import patch
from luda.common import DesktopError
from luda.x11 import X11

class X11Tests(unittest.TestCase):
    @patch('luda.x11.run',return_value=b'{"result": 1}')
    def test_every_read_opens_a_new_helper(self, run):
        x=X11();self.assertEqual(x.root,1);self.assertEqual(x.root,1);x.close();self.assertEqual(x.root,1)
        self.assertEqual(run.call_count,4)
        self.assertEqual(run.call_args.kwargs['timeout'],2)
        self.assertEqual(json.loads(run.call_args.kwargs['data'])['method'],'root')
    @patch('luda.x11.run',side_effect=DesktopError('TIMEOUT','test'))
    def test_timeout_is_preserved(self, run):
        with self.assertRaises(DesktopError) as e:X11()
        self.assertEqual(e.exception.code,'TIMEOUT')
    @patch('luda.x11.run',side_effect=DesktopError('CANCELLED','test'))
    def test_cancellation_is_preserved(self, run):
        with self.assertRaises(DesktopError) as e:X11()
        self.assertEqual(e.exception.code,'CANCELLED')
    @patch('luda.x11.run',side_effect=DesktopError('BACKEND_ERROR','Xlib fatal I/O'))
    def test_crashed_helper_is_display_error(self, run):
        with self.assertRaises(DesktopError) as e:X11()
        self.assertEqual(e.exception.code,'DISPLAY_UNAVAILABLE')
    @patch('luda.x11.run',return_value=b'{"error":{"code":"STALE_TARGET","message":"gone"}}')
    def test_native_error_retains_code(self, run):
        with self.assertRaises(DesktopError) as e:X11()
        self.assertEqual(e.exception.code,'STALE_TARGET')
    def test_malformed_response_rejected(self):
        for raw in (b'not json',b'[]',b'{}',b'{"error":{}}'):
            with self.subTest(raw=raw),patch('luda.x11.run',return_value=raw),self.assertRaises(DesktopError) as e:X11()
            self.assertEqual(e.exception.code,'BACKEND_ERROR')
    @patch('luda.x11.run',return_value=b'{"result":1}')
    def test_invalid_xids_and_limits_do_not_launch(self, run):
        x=X11();run.reset_mock()
        for value in (0,-1,True,None,1.5,'1',2**32):
            with self.subTest(value=value),self.assertRaises(DesktopError):x.geometry(value)
        for value in (0,-1,True,None,4097):
            with self.subTest(limit=value),self.assertRaises(DesktopError):x.popup_surfaces(value)
        run.assert_not_called()

if __name__ == '__main__':unittest.main()
