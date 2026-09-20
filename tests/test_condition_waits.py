import threading
import time
import unittest
from unittest.mock import Mock

from luda.common import DesktopError, operation_scope
from luda.waits import ConditionWaitsMixin


class WaitFixture(ConditionWaitsMixin):
    pass


def tree(nodes=(),**values):
    return {'nodes':list(nodes),'available':True,'truncated':False,'unreadable_nodes':0,**values}


class ConditionWaits(unittest.TestCase):
    def setUp(self):
        self.desktop=WaitFixture()
        self.desktop.inspect=Mock()
        self.desktop.observe=Mock()
        self.desktop.wait_for=Mock(return_value={'matched':True})

    def test_presence_reacquires_fresh_element_ids(self):
        node={'element_id':'new-id','name':'Ready'}
        self.desktop.inspect.side_effect=[tree(),tree([node])]
        value=self.desktop.wait_condition('element_present',window_id='w',name='Ready',timeout=.5)
        self.assertEqual(value['elements'],[node])
        self.assertEqual(self.desktop.inspect.call_count,2)
        self.assertEqual(self.desktop.inspect.call_args.kwargs['name'],'Ready')

    def test_absence_requires_complete_available_tree(self):
        for changes in ({'truncated':True},{'available':False},{'unreadable_nodes':1},{'unreadable_branches':1},{'truncation':{'depth_pruned':True}}):
            with self.subTest(changes=changes):
                self.desktop.inspect.return_value=tree(**changes)
                with self.assertRaises(DesktopError) as raised:
                    self.desktop.wait_condition('element_absent',window_id='w',name='Missing')
                self.assertEqual(raised.exception.code,'VERIFICATION_LIMIT')

    def test_observed_presence_can_be_partial_but_says_so(self):
        self.desktop.inspect.return_value=tree([{'element_id':'new'}],truncated=True)
        value=self.desktop.wait_condition('element_present',window_id='w',role='button')
        self.assertTrue(value['matched'])
        self.assertFalse(value['coverage_complete'])

    def test_disappearance_refreshes_until_absent(self):
        self.desktop.inspect.side_effect=[tree([{'element_id':'old'}]),tree()]
        self.assertTrue(self.desktop.wait_condition('element_absent',window_id='w',name='Old')['matched'])

    def test_invalid_and_empty_filters_never_observe(self):
        for arguments in ({},{'name':''},{'name':' '},{'states':[]},{'states':['']},{'name':3},{'name':'x','element_id':'e'},{'name':'x','timeout':float('nan')}):
            with self.subTest(arguments=arguments),self.assertRaises(DesktopError):
                self.desktop.wait_condition('element_present',window_id='w',**arguments)
        self.desktop.inspect.assert_not_called()

    def test_existing_conditions_delegate_without_new_filters(self):
        self.assertTrue(self.desktop.wait_condition('window_present',window_id='w')['matched'])
        self.desktop.wait_for.assert_called_once()
        with self.assertRaises(DesktopError):
            self.desktop.wait_condition('window_present',window_id='w',name='unexpected')

    def test_sampled_pixels_require_elapsed_stable_interval(self):
        self.desktop._pixel_sample=Mock(return_value='same')
        began=time.monotonic()
        value=self.desktop.wait_condition('pixels_stable',window_id='w',stable_for=.1,timeout=.5)
        self.assertTrue(value['matched'])
        self.assertGreaterEqual(time.monotonic()-began,.1)
        self.assertIn('not application idleness',value['verification'])

    def test_continuous_animation_times_out_without_match(self):
        count=iter(range(100))
        self.desktop._pixel_sample=Mock(side_effect=lambda _:next(count))
        value=self.desktop.wait_condition('pixels_stable',window_id='w',stable_for=.1,timeout=.2)
        self.assertFalse(value['matched'])
        self.assertEqual(value['effect'],'none')

    def test_cancelled_parent_is_inherited(self):
        cancel=threading.Event()
        self.desktop.inspect.return_value=tree()
        timer=threading.Timer(.05,cancel.set)
        timer.start()
        try:
            with operation_scope(cancelled=cancel),self.assertRaises(DesktopError) as raised:
                self.desktop.wait_condition('element_present',window_id='w',name='never',timeout=2)
            self.assertEqual(raised.exception.code,'CANCELLED')
        finally:
            timer.cancel()

    def test_parent_guard_remains_active(self):
        def guard():
            raise DesktopError('PAUSED','Fixture pause')
        with operation_scope(guard=guard),self.assertRaises(DesktopError) as raised:
            self.desktop.wait_condition('element_present',window_id='w',name='never')
        self.assertEqual(raised.exception.code,'PAUSED')
        self.desktop.inspect.assert_not_called()

    def test_invalid_stability_parameters_do_not_capture(self):
        for options in ({'stable_for':0},{'stable_for':True},{'stable_for':float('nan')},{'stable_for':2,'timeout':1},{'name':'unexpected'}):
            with self.subTest(options=options),self.assertRaises(DesktopError):
                self.desktop.wait_condition('pixels_stable',window_id='w',**options)
        self.desktop.observe.assert_not_called()


if __name__=='__main__':
    unittest.main()
