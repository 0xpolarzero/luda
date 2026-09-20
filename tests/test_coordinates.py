"""Enumerated integer-pointer oracle independent of the bounds formula."""
import copy
import unittest
from unittest.mock import Mock,patch
from PIL import Image
from luda.coordinates import image_bounds
from luda.desktop import Desktop


def oracle(rect,native,image):
    columns=[x for x in range(image[0]) if rect['x']<=x*native[0]//image[0]<rect['x']+rect['width']]
    rows=[y for y in range(image[1]) if rect['y']<=y*native[1]//image[1]<rect['y']+rect['height']]
    return None if not columns or not rows else {'x':columns[0],'y':rows[0],'width':len(columns),'height':len(rows)}


class Coordinates(unittest.TestCase):
    def test_small_rectangles_exhaustive_against_independent_mapping(self):
        for native,image in (((13,9),(7,5)),((10,11),(3,8)),((5,4),(5,4)),((4,3),(7,5))):
            for x in range(-3,native[0]+3):
                for y in range(-2,native[1]+2):
                    for width,height in ((1,1),(3,2),(7,8),(0,4),(4,0)):
                        rect={'x':x,'y':y,'width':width,'height':height}
                        self.assertEqual(image_bounds(rect,native,image),oracle(rect,native,image),(rect,native,image))
    def test_tall_resized_image_uses_independent_axis_ratios(self):
        native=(90,9000);image=(26,2560)
        for rect in ({'x':13,'y':7001,'width':22,'height':817},{'x':-20,'y':8995,'width':110,'height':30}):
            self.assertEqual(image_bounds(rect,native,image),oracle(rect,native,image))
    def test_last_pixel_and_unsampled_sliver(self):
        rect={'x':9,'y':9,'width':1,'height':1}
        self.assertEqual(image_bounds(rect,(10,10),(10,10)),rect)
        self.assertIsNone(image_bounds(rect,(10,10),(3,3)))
    def test_invalid_dimensions_refused(self):
        with self.assertRaises(ValueError):image_bounds({'x':0,'y':0,'width':1,'height':1},(0,10),(3,3))
    def test_observe_enriches_copies_without_changing_native_cache(self):
        d=Desktop();self.addCleanup(d.close);d.x=Mock();d.x.root=1
        d.x.geometry.return_value={'width':90,'height':9000}
        window={'window_id':'w','bounds':{'x':-10,'y':7000,'width':50,'height':1200},'active':True,'workspace':0}
        popup={'popup_id':'p','owner_window_id':'w','xid':4,'generation':'g','bounds':{'x':50,'y':8500,'width':20,'height':700}}
        original_window=copy.deepcopy(window);original_popup=copy.deepcopy(popup)
        d.list_windows=Mock(return_value=[window]);d.observe_popups=Mock(return_value=[popup]);d.popup_signature=lambda values:values
        def capture(args,**kwargs):Image.new('RGB',(90,9000)).save(args[-1])
        with patch('luda.desktop.run',side_effect=capture):result=d.observe()
        self.assertEqual(result['windows'][0]['image_bounds'],oracle(window['bounds'],(90,9000),(26,2560)))
        self.assertEqual(result['popups'][0]['image_bounds'],oracle(popup['bounds'],(90,9000),(26,2560)))
        self.assertEqual(window,original_window);self.assertEqual(popup,original_popup)
        snapshot=d.snapshots[result['snapshot_id']]
        self.assertEqual(snapshot['popups'],[original_popup]);self.assertNotIn('image_bounds',snapshot['popups'][0])
        self.assertEqual(snapshot['signature'],d.signature([original_window]))
        self.assertEqual(result['coordinate_spaces']['bounds'],'native_x11_root_pixels')
    def test_inspect_declares_native_or_unavailable_not_snapshot_pixels(self):
        for space in ('screen','unavailable'):
            d=Desktop();self.addCleanup(d.close)
            d.target_window=Mock(return_value={'pid':42,'start':'1','bounds':{},'frame_bounds':{},'title':'fixture'})
            d.ax=Mock(return_value={'nodes':[],'bounds_coordinates':space})
            result=d.inspect('w')
            self.assertEqual(result['bounds_coordinate_space'],'unavailable' if space=='unavailable' else 'native_x11_root_pixels')
            self.assertNotIn('snapshot_id',result)
if __name__=='__main__':unittest.main()
