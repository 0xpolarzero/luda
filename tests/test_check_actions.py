"""Directional Chromium/Electron check actions require observed desired state."""
import unittest
from unittest.mock import patch
from test_semantic import w

class CheckActions(unittest.TestCase):
    def test_directional_actions_and_idempotence(self):
        states=set();calls=[]
        class Node:
            def get_action_iface(self):return self
            def do_action(self,index):
                calls.append(index)
                if desired:states.add('checked')
                else:states.discard('checked')
                return True
        node=Node()
        with patch.object(w,'states_of',lambda _:states),patch.object(w,'verify',lambda fn:fn()):
            for desired,action in ((True,'check'),(False,'uncheck')):
                current={'states':list(states),'role':'check box','actions':[action,'showContextMenu']}
                response=w.semantic(node,current,{'op':'check','checked':desired})
                self.assertEqual(response['effect'],'verified')
                count=len(calls)
                self.assertFalse(w.semantic(node,current,{'op':'check','checked':desired})['changed'])
                self.assertEqual(len(calls),count)
        self.assertEqual(calls,[0,0])
    def test_wrong_direction_never_invoked(self):
        with patch.object(w,'states_of',return_value=set()):
            result=w.semantic(object(),{'states':[],'role':'check box','actions':['uncheck']},{'op':'check','checked':True})
        self.assertEqual(result['error'],'UNSUPPORTED_ACTION')
    def test_accepted_but_unchanged_is_uncertain(self):
        class Node:
            def get_action_iface(self):return self
            def do_action(self,index):return True
        with patch.object(w,'states_of',return_value=set()),patch.object(w,'verify',lambda fn:fn()):
            result=w.semantic(Node(),{'states':[],'role':'check box','actions':['check']},{'op':'check','checked':True})
        self.assertEqual(result['effect'],'uncertain')
        self.assertFalse(result['checked'])

if __name__=='__main__':unittest.main()
