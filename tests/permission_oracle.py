"""Receive whole permission snapshots without treating network order as event order."""
import time

class PermissionOracle:
    def __init__(self):
        self.state={}
        self.reports=[]

    def accept(self,value):
        sequence=value.get('sequence')
        if type(sequence) is not int or sequence<1:
            raise ValueError('Permission report needs a positive event sequence')
        if len(self.reports)>=64:
            raise ValueError('Unexpected number of permission reports')
        document=value.get('document')
        if not isinstance(document,str) or not document:
            raise ValueError('Permission report needs its page generation')
        applied=(not self.state or document==self.state['document']) and sequence>self.state.get('sequence',0)
        self.reports.append({'received_at':time.monotonic(),'applied':applied,'snapshot':dict(value)})
        if applied:self.state=dict(value)
        return applied
