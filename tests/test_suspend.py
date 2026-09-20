import unittest
from unittest.mock import patch
from luda.desktop import Desktop
from luda.timing import elapsed_time

class SuspendTests(unittest.TestCase):
    def test_elapsed_clock_ignores_wall_clock_and_includes_suspend(self):
        with patch('luda.timing.time.clock_gettime',return_value=1234) as clock:
            self.assertEqual(elapsed_time(),1234)
            clock.assert_called_once()
    def test_suspend_invalidates_observations_and_elements(self):
        with patch('luda.desktop.suspend_offset',side_effect=[0,0,1,1]):
            d=Desktop();self.addCleanup(d.close)
            d.snapshots['s']={};d.elements['e']={}
            with d.transaction():self.assertIn('s',d.snapshots)
            with d.transaction():
                self.assertEqual(d.snapshots,{})
                self.assertEqual(d.elements,{})
            d.snapshots['new']={}
            with d.transaction():self.assertIn('new',d.snapshots)
    def test_sampling_jitter_does_not_invalidate(self):
        with patch('luda.desktop.suspend_offset',side_effect=[0,.001]):
            d=Desktop();self.addCleanup(d.close);d.snapshots['s']={}
            with d.transaction():self.assertIn('s',d.snapshots)

if __name__=='__main__':unittest.main()
