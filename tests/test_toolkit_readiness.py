"""Delayed provider readiness is distinct from failed mutation or ambiguous scope."""
import unittest
from luda.common import DesktopError
from toolkit_readiness import wait_for_accessibility
class Readiness(unittest.TestCase):
    def test_delayed_provider_ready_without_mutating(self):
        now=[0];calls=[];evidence=[]
        def inspect():
            calls.append('read')
            if len(calls)<3:raise DesktopError('ACCESSIBILITY_UNAVAILABLE','registering')
            return {'available':True,'nodes':[{'name':'Toolkit text'}]}
        result=wait_for_accessibility(inspect,clock=lambda:now[0],sleep=lambda n:now.__setitem__(0,now[0]+n),evidence=evidence)
        self.assertTrue(result['available']);self.assertEqual(calls,['read']*3)
        self.assertEqual([x['ready'] for x in evidence],[False,False,True])
    def test_ambiguity_is_not_retried(self):
        calls=[]
        def inspect():calls.append(1);raise DesktopError('AMBIGUOUS_ACCESSIBILITY_WINDOW','multiple')
        with self.assertRaises(DesktopError) as raised:wait_for_accessibility(inspect)
        self.assertEqual(raised.exception.code,'AMBIGUOUS_ACCESSIBILITY_WINDOW');self.assertEqual(len(calls),1)
    def test_unavailable_preserved_after_deadline(self):
        now=[0]
        def inspect():raise DesktopError('ACCESSIBILITY_UNAVAILABLE','absent')
        with self.assertRaises(DesktopError) as raised:
            wait_for_accessibility(inspect,timeout=.2,clock=lambda:now[0],sleep=lambda n:now.__setitem__(0,now[0]+n))
        self.assertEqual(raised.exception.code,'ACCESSIBILITY_UNAVAILABLE');self.assertLessEqual(now[0],.2)
    def test_empty_tree_does_not_satisfy_ready(self):
        with self.assertRaises(DesktopError):wait_for_accessibility(lambda:{'available':True,'nodes':[]},timeout=0)
if __name__=='__main__':unittest.main()
