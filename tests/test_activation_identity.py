"""An active reused XID is not verification of the original window generation."""
from contextlib import nullcontext
import unittest
from unittest.mock import Mock,patch
from luda.common import DesktopError
from luda.desktop import Desktop

class ActivationIdentity(unittest.TestCase):
    def driver(self,after):
        d=Desktop.__new__(Desktop)
        original={'window_id':'original-generation','xid':99,'active':False}
        d.list_windows=Mock(side_effect=[[original],after])
        d.active=Mock(return_value=777)
        d.input_scope=Mock(side_effect=lambda:nullcontext())
        d._raise_window=Mock(return_value={'effect':'verified'})
        d.focus_input=Mock()
        self.enterContext(patch('luda.interaction.properties',return_value=''))
        return d
    def test_reused_active_xid_does_not_verify_original_generation(self):
        d=self.driver([{'window_id':'replacement-generation','xid':99,'active':True}])
        with patch('luda.desktop.run'),self.assertRaises(DesktopError) as caught:d.activate('original-generation')
        self.assertEqual(caught.exception.code,'STALE_TARGET')
        self.assertEqual(caught.exception.effect,'uncertain')
        d.focus_input.assert_not_called()
    def test_same_generation_active_is_verified(self):
        d=self.driver([{'window_id':'original-generation','xid':99,'active':True}])
        with patch('luda.desktop.run') as run:
            result=d.activate('original-generation')
        self.assertEqual(result['effect'],'verified')
        d._raise_window.assert_called_once()
        d.focus_input.assert_called_once_with({'window_id':'original-generation','xid':99,'active':True})
        d.active.assert_not_called()
        run.assert_not_called()
    def test_post_dispatch_lookup_failure_retains_uncertainty(self):
        d=self.driver([])
        d.list_windows.side_effect=[ [{'window_id':'original-generation','xid':99,'active':False}], DesktopError('RESOURCE_UNAVAILABLE','resources') ]
        with patch('luda.desktop.run'),self.assertRaises(DesktopError) as caught:d.activate('original-generation')
        self.assertEqual(caught.exception.code,'RESOURCE_UNAVAILABLE')
        self.assertEqual(caught.exception.effect,'uncertain')
        d.focus_input.assert_not_called()

if __name__=='__main__':unittest.main()
