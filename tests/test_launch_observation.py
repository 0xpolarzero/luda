import threading
import unittest
from types import SimpleNamespace
from unittest.mock import Mock,patch
from luda.apps import launch_and_observe
from luda.common import DesktopError,operation_scope

class LaunchObservationTests(unittest.TestCase):
    def launch(self):
        return {'effect':'dispatched','spawned_processes':[{'pid':42,'start':'123'}]}
    def window(self,n=1,start='123'):
        return {'window_id':str(n),'pid':42,'start':start,'title':'Observed','active':True,'private':'excluded'}
    def run_case(self,windows,**kwargs):
        desktop=SimpleNamespace(list_windows=Mock(return_value=windows),window_diagnostics={})
        with patch('luda.apps.launch_application',return_value=self.launch()) as launch, patch('luda.apps.time.monotonic',side_effect=[0,1]):
            result=launch_and_observe(desktop,'fixture.desktop',wait_timeout=.1,**kwargs)
        launch.assert_called_once()
        return result['window_observation']
    def test_process_generation_match_and_payload_whitelist(self):
        result=self.run_case([self.window(),self.window(2,start='124')])
        self.assertEqual(result['state'],'one_candidate')
        self.assertEqual([w['window_id'] for w in result['candidates']],['1'])
        self.assertNotIn('private',result['candidates'][0])
    def test_multiple_and_truncation_never_unique(self):
        result=self.run_case([self.window(n) for n in range(55)])
        self.assertEqual((result['state'],result['total_candidates'],len(result['candidates']),result['truncated']),('multiple_candidates',55,50,True))
    def test_missing_windows_and_missing_association_distinct(self):
        self.assertEqual(self.run_case([])['state'],'pending')
        desktop=Mock()
        with patch('luda.apps.launch_application',return_value={'effect':'dispatched','spawned_pids':[42]}):
            result=launch_and_observe(desktop,'fixture.desktop')
        self.assertEqual(result['window_observation']['state'],'unassociated');desktop.list_windows.assert_not_called()
    def test_zero_does_not_enumerate(self):
        desktop=Mock()
        with patch('luda.apps.launch_application',return_value=self.launch()):
            result=launch_and_observe(desktop,'fixture.desktop',wait_timeout=0)
        self.assertEqual(result['window_observation']['state'],'not_requested');desktop.list_windows.assert_not_called()
    def test_incomplete_enumeration_not_unique(self):
        desktop=SimpleNamespace(list_windows=lambda:[self.window()],window_diagnostics={'unavailable_count':1})
        with patch('luda.apps.launch_application',return_value=self.launch()),patch('luda.apps.time.monotonic',side_effect=[0,1]):
            result=launch_and_observe(desktop,'fixture.desktop',wait_timeout=.1)
        self.assertEqual(result['window_observation']['state'],'unavailable')
        self.assertEqual(result['window_observation']['unavailable_windows'],1)
    def test_postlaunch_failure_retains_effect_and_sanitizes(self):
        desktop=Mock();desktop.list_windows.side_effect=DesktopError('BACKEND_ERROR','private detail')
        with patch('luda.apps.launch_application',return_value=self.launch()):result=launch_and_observe(desktop,'fixture.desktop')
        self.assertEqual(result['effect'],'dispatched');self.assertNotIn('private detail',str(result))
    def test_shared_cancellation_never_relaunches_or_claims_no_effect(self):
        cancelled=threading.Event()
        def launched(*args):cancelled.set();return self.launch()
        with patch('luda.apps.launch_application',side_effect=launched) as launch,operation_scope(cancelled=cancelled):
            with self.assertRaises(DesktopError) as caught:launch_and_observe(Mock(),'fixture.desktop')
        self.assertEqual(caught.exception.code,'CANCELLED');self.assertEqual(caught.exception.effect,'uncertain');launch.assert_called_once()
    def test_shared_deadline_bounds_observation_after_dispatch(self):
        desktop=SimpleNamespace(list_windows=lambda:[],window_diagnostics={})
        with patch('luda.apps.launch_application',return_value=self.launch()) as launch,operation_scope(timeout=.01):
            with self.assertRaises(DesktopError) as caught:launch_and_observe(desktop,'fixture.desktop',wait_timeout=3)
        self.assertEqual((caught.exception.code,caught.exception.effect),('TIMEOUT','uncertain'));launch.assert_called_once()
    def test_cancellation_inside_final_enumeration_is_not_swallowed(self):
        for error in (None,DesktopError('BACKEND_ERROR','private')):
            cancelled=threading.Event()
            def enumerate_windows():
                cancelled.set()
                if error:raise error
                return []
            desktop=SimpleNamespace(list_windows=enumerate_windows,window_diagnostics={})
            with self.subTest(error=error),patch('luda.apps.launch_application',return_value=self.launch()) as launch,patch('luda.apps.time.monotonic',side_effect=[0,5]),operation_scope(cancelled=cancelled):
                with self.assertRaises(DesktopError) as caught:launch_and_observe(desktop,'fixture.desktop',wait_timeout=.1)
            self.assertEqual((caught.exception.code,caught.exception.effect),('CANCELLED','uncertain'));launch.assert_called_once()
    def test_invalid_wait_before_dispatch(self):
        with patch('luda.apps.launch_application') as launch:
            for value in (True,'1',None,-1,3.1,float('nan'),float('inf')):
                with self.subTest(value=value),self.assertRaises(DesktopError):launch_and_observe(Mock(),'fixture.desktop',wait_timeout=value)
        launch.assert_not_called()

if __name__=='__main__':unittest.main()
