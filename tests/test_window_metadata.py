import unittest
from unittest.mock import Mock,patch
from luda._x11_helper import _NativeX11,_decode_frame_extents,_decode_wm_class
from luda.common import DesktopError
from luda.x11 import X11

class MetadataTests(unittest.TestCase):
    def test_frame_extents_are_exact_bounded_cardinals(self):
        self.assertEqual(_decode_frame_extents((6,32,[1,2,3,4],0)),{'left':1,'right':2,'top':3,'bottom':4})
        for prop in [(31,32,[1,2,3,4],0),(6,8,b'abcd',0),(6,32,[1,2],0),(6,32,[1,2,3,4],4),(6,32,[1,2,3,2**32-1],0)]:
            with self.subTest(prop=prop),self.assertRaises(DesktopError):_decode_frame_extents(prop)
    def test_class_strings_preserve_unicode_and_escapes(self):
        raw='日本語 instance\0Class "quoted"\\literal\0'.encode()
        self.assertEqual(_decode_wm_class((31,8,raw,0)),['日本語 instance','Class "quoted"\\literal'])
        self.assertEqual(_decode_wm_class((31,8,b'caf\xe9\0Class\0',0)),['café','Class'])
    def test_class_wrong_types_structure_and_size_rejected(self):
        for prop in [(6,8,b'a\0b\0',0),(31,32,[1,2],0),(31,8,b'a\0b',0),(31,8,b'a\0b\0extra\0',0),(31,8,b'a\0b\0',5),(31,8,b'a'*1025,0)]:
            with self.subTest(prop=prop),self.assertRaises(DesktopError):_decode_wm_class(prop)
    def native(self):
        native=_NativeX11.__new__(_NativeX11)
        native.geometry=Mock(return_value={'x':0,'y':0,'width':100,'height':100})
        native._property=Mock(return_value=None)
        return native
    def test_generation_change_explicitly_excludes_window(self):
        native=self.native();native.window_tokens=Mock(side_effect=[{1:'first',2:'stable'},{1:'new',2:'stable'}])
        result=native.window_metadata([1,1,2])
        self.assertEqual(result['requested_count'],3);self.assertEqual(result['unique_requested_count'],2)
        self.assertEqual(result['returned_count'],1);self.assertEqual(result['unavailable'],[{'xid':1,'code':'STALE_TARGET'}])
        self.assertEqual(len(result['windows'][2]['unavailable_properties']),3)
    def test_bad_generation_does_not_hide_other_windows(self):
        native=self.native()
        def tokens(ids):
            if 1 in ids:raise DesktopError('INVALID_WINDOW_TOKEN','bad')
            return {2:'stable'}
        native.window_tokens=Mock(side_effect=tokens)
        result=native.window_metadata([1,2])
        self.assertEqual(result['returned_count'],1);self.assertEqual(result['unavailable'],[{'xid':1,'code':'INVALID_WINDOW_TOKEN'}])
    def test_empty_batch_has_explicit_zero_counts(self):
        native=self.native();native.window_tokens=Mock(return_value={})
        self.assertEqual(native.window_metadata([]),{'windows':{},'unavailable':[],'requested_count':0,'unique_requested_count':0,'returned_count':0,'unavailable_count':0})
    @patch('luda.x11.run',return_value=b'{"result":1}')
    def test_public_batch_bound_rejects_before_helper(self,run):
        x=X11();run.reset_mock()
        for ids in (None,[0],[True],list(range(1,514))):
            with self.subTest(ids=ids),self.assertRaises(DesktopError):x.window_metadata(ids)
        run.assert_not_called()

if __name__=='__main__':unittest.main()
