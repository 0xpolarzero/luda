import unittest
from unittest.mock import Mock,patch
from luda.common import DesktopError
from luda.desktop import Desktop

class WindowEnumerationTests(unittest.TestCase):
    def driver(self):
        d=Desktop.__new__(Desktop);d.windows={};d.active=Mock(return_value=None)
        return d
    def test_disappearing_dialog_retries_read_only_enumeration(self):
        d=self.driver()
        with patch('luda.desktop.run',side_effect=[DesktopError('BACKEND_ERROR','BadWindow X_GetProperty'),b'']) as run:
            self.assertEqual(d.list_windows(),[])
        self.assertEqual(run.call_count,2)
        self.assertTrue(all(c.args[0]==['wmctrl','-lp'] for c in run.call_args_list))
    def test_repeated_race_stops_after_three_attempts(self):
        with patch('luda.desktop.run',side_effect=DesktopError('BACKEND_ERROR','BadWindow X_GetProperty')) as run,self.assertRaises(DesktopError):self.driver().list_windows()
        self.assertEqual(run.call_count,3)
    def test_other_failures_and_cancellation_not_retried(self):
        for error in [DesktopError('BACKEND_ERROR','cannot connect'),DesktopError('CANCELLED','BadWindow X_GetProperty')]:
            with patch('luda.desktop.run',side_effect=error) as run,self.assertRaises(DesktopError):self.driver().list_windows()
            self.assertEqual(run.call_count,1)

if __name__=='__main__':unittest.main()

class WindowMetadataIntegrationTests(unittest.TestCase):
    def driver(self,metadata):
        d=Desktop.__new__(Desktop);d.windows={};d.active=Mock(return_value=16)
        display=Mock();display.window_metadata.return_value={'windows':metadata,'unavailable':[]}
        d.display=Mock(return_value=display)
        return d
    def metadata(self,pid=42,generation='a'*32):
        return {'pid':pid,'generation':generation,'bounds':{'x':10,'y':20,'width':100,'height':80},
                'frame_extents':{'left':2,'right':2,'top':18,'bottom':2},'wm_class':['app','App'],
                'unavailable_properties':[]}
    def test_one_metadata_batch_and_no_per_window_xprop(self):
        d=self.driver({16:self.metadata()})
        with patch('luda.desktop.run',return_value=b'0x10 0 42 host Test window\n') as run,patch('luda.desktop.process_identity',return_value='start'):
            windows=d.list_windows()
        self.assertEqual(windows[0]['frame_bounds'],{'x':8,'y':2,'width':104,'height':100})
        self.assertTrue(windows[0]['window_id'].endswith('a'*32))
        run.assert_called_once_with(['wmctrl','-lp'])
        d.display().window_metadata.assert_called_once_with([16])
    def test_reused_window_owner_never_gets_old_identity(self):
        d=self.driver({16:self.metadata(pid=99)})
        with patch('luda.desktop.run',return_value=b'0x10 0 42 host Test\n'):
            result=d.window_overview()
        self.assertFalse(result['windows']);self.assertEqual(result['unavailable'][0]['code'],'WINDOW_OWNER_CHANGED')
    def test_filtering_and_pagination_keep_full_internal_target_set(self):
        d=self.driver({});windows=[{'title':'Editor '+str(i),'wm_class':['Test'],'window_id':str(i)} for i in range(7)]
        d.list_windows=Mock(return_value=windows)
        result=d.window_overview('EDITOR',2,2)
        self.assertEqual([w['window_id'] for w in result['windows']],['2','3'])
        self.assertEqual(result['total_matches'],7);self.assertEqual(result['next_offset'],4)
        self.assertTrue(result['truncated'])
        self.assertEqual(d.window_overview('absent')['total_matches'],0)
    def test_invalid_pagination_never_enumerates(self):
        d=self.driver({});d.list_windows=Mock()
        for args in ({'limit':True},{'offset':-1},{'query':123},{'limit':201}):
            with self.subTest(args=args),self.assertRaises(DesktopError):d.window_overview(**args)
        d.list_windows.assert_not_called()
