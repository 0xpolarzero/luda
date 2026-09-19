import unittest
from unittest.mock import patch
from luda._x11_helper import _decode_window_token
from luda.common import DesktopError
from luda.x11 import X11

class WindowTokenTests(unittest.TestCase):
    def test_missing_and_valid_property(self):
        self.assertIsNone(_decode_window_token(0,0,b'',0))
        self.assertEqual(_decode_window_token(31,8,b'0123456789abcdef0123456789abcdef',0),'0123456789abcdef0123456789abcdef')
    def test_malformed_property_types_lengths_and_bytes(self):
        valid=b'a'*32
        cases=[(6,8,valid,0),(31,32,valid,0),(31,8,valid,1),(31,8,b'',0),(31,8,b'a'*31,0),(31,8,b'a'*33,0),(31,8,b'A'*32,0),(31,8,b'g'*32,0),(31,8,b'\0'*32,0),(31,8,b'\xff'*32,0)]
        for args in cases:
            with self.subTest(args=args),self.assertRaises(DesktopError) as exc:_decode_window_token(*args)
            self.assertEqual(exc.exception.code,'INVALID_WINDOW_TOKEN')
    @patch('luda.x11.run',return_value=b'{"result":1}')
    def test_invalid_batch_does_not_launch(self,run):
        x=X11();run.reset_mock()
        for ids in (None,'1',[False],[0],[2**32],list(range(1,514))):
            with self.subTest(ids=ids),self.assertRaises(DesktopError):x.window_tokens(ids)
        run.assert_not_called()
    @patch('luda.x11.run',side_effect=[b'{"result":1}',b'{"result":{"12":"0123456789abcdef0123456789abcdef"}}'])
    def test_token_result_integer_keys(self,run):
        x=X11()
        self.assertEqual(x.window_tokens([12]),{12:'0123456789abcdef0123456789abcdef'})

if __name__=='__main__':unittest.main()
