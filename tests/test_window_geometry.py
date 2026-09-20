"""Post-dispatch observations must not upgrade effects or cross generations."""
import unittest
from unittest.mock import patch
from luda.common import DesktopError
from luda.interaction import InteractionMixin


class GeometryDriver(InteractionMixin):
    def __init__(self):
        self.window={'window_id':'generation-a','xid':42,
                     'bounds':{'x':12,'y':30,'width':320,'height':200},
                     'frame_bounds':{'x':10,'y':10,'width':324,'height':222}}
        self.effect='dispatched'
    def target_window(self,*args): return self.window
    def _await_state(self,predicate,extra): return {'effect':self.effect,**extra}


class WindowGeometryTests(unittest.TestCase):
    @patch('luda.interaction.run',return_value=b'_NET_WM_STATE = ')
    def test_constrained_resize_returns_actual_bounds_without_false_verification(self,run):
        result=GeometryDriver().manage_window('generation-a','resize',width=100,height=100)
        self.assertEqual(result['effect'],'dispatched')
        actual=result['observed_geometry']
        self.assertEqual(actual['client_bounds']['width'],320)
        self.assertEqual(actual['request_match'],'nonmatching')
        self.assertEqual(actual['constraint_reason'],'not_determined')
        self.assertEqual(actual['requested'],{'width':100,'height':100})
    @patch('luda.interaction.run',return_value=b'')
    def test_late_matching_observation_does_not_upgrade_dispatch(self,run):
        result=GeometryDriver().manage_window('generation-a','resize',width=320,height=200)
        self.assertEqual(result['effect'],'dispatched')
        self.assertEqual(result['observed_geometry']['request_match'],'matched')
    @patch('luda.interaction.run',return_value=b'')
    def test_later_geometry_change_downgrades_prior_match(self,run):
        driver=GeometryDriver();driver.effect='verified'
        self.assertEqual(driver.manage_window('generation-a','resize',width=500,height=400)['effect'],'dispatched')
    @patch('luda.interaction.run',return_value=b'')
    def test_move_compares_frame_not_client_position(self,run):
        driver=GeometryDriver();driver.effect='verified'
        result=driver.manage_window('generation-a','move',x=10,y=10)
        self.assertEqual(result['effect'],'verified')
        self.assertEqual(result['observed_geometry']['request_match'],'matched')
    @patch('luda.interaction.run',return_value=b'_NET_WM_STATE_MAXIMIZED_HORZ, _NET_WM_STATE_MAXIMIZED_VERT')
    def test_maximize_reports_state_and_bounds_without_restore_promise(self,run):
        result=GeometryDriver().manage_window('generation-a','maximize')
        observed=result['observed_geometry']
        self.assertTrue(observed['wm_state']['maximized_horizontal'])
        self.assertNotIn('restored',observed)
        self.assertNotIn('requested',observed)
    @patch('luda.interaction.run',return_value=b'')
    def test_replacement_during_postdispatch_property_read_is_uncertain(self,run):
        driver=GeometryDriver()
        with patch.object(driver,'target_window',side_effect=[driver.window,driver.window,DesktopError('STALE_TARGET','replacement')]):
            with self.assertRaises(DesktopError) as caught:
                driver.manage_window('generation-a','resize',width=320,height=200)
        self.assertEqual(caught.exception.code,'STALE_TARGET')
        self.assertEqual(caught.exception.effect,'uncertain')
    @patch('luda.interaction.run')
    def test_stale_initial_identity_never_dispatches(self,run):
        driver=GeometryDriver()
        with patch.object(driver,'target_window',side_effect=DesktopError('STALE_TARGET','gone')):
            with self.assertRaises(DesktopError):driver.manage_window('generation-a','maximize')
        run.assert_not_called()

    @patch('luda.interaction.run',return_value=b'')
    def test_later_wm_state_change_downgrades_prior_match(self,run):
        driver=GeometryDriver();driver.effect='verified'
        self.assertEqual(driver.manage_window('generation-a','maximize')['effect'],'dispatched')
