"""An active reused XID is not verification of the original window generation."""
import unittest
from unittest.mock import Mock,patch
from luda.common import DesktopError
from luda.desktop import Desktop

class ActivationIdentity(unittest.TestCase):
    def driver(self,after):
        d=Desktop.__new__(Desktop)
        original={'window_id':'original-generation','xid':99,'active':False}
        d.list_windows=Mock(side_effect=[[original],after])
        d.active=Mock(return_value=99)
        return d
    def test_reused_active_xid_does_not_verify_original_generation(self):
        d=self.driver([{'window_id':'replacement-generation','xid':99,'active':True}])
        with patch('luda.desktop.run'),self.assertRaises(DesktopError) as caught:d.activate('original-generation')
        self.assertEqual(caught.exception.code,'STALE_TARGET')
        self.assertEqual(caught.exception.effect,'uncertain')
    def test_same_generation_active_is_verified(self):
        d=self.driver([{'window_id':'original-generation','xid':99,'active':True}])
        with patch('luda.desktop.run') as run:
            result=d.activate('original-generation')
        self.assertEqual(result['effect'],'verified');run.assert_called_once()
    def test_post_dispatch_lookup_failure_retains_uncertainty(self):
        d=self.driver([])
        d.list_windows.side_effect=[ [{'window_id':'original-generation','xid':99,'active':False}], DesktopError('RESOURCE_UNAVAILABLE','resources') ]
        with patch('luda.desktop.run'),self.assertRaises(DesktopError) as caught:d.activate('original-generation')
        self.assertEqual(caught.exception.code,'RESOURCE_UNAVAILABLE')
        self.assertEqual(caught.exception.effect,'uncertain')

if __name__=='__main__':unittest.main()
