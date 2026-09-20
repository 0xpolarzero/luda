"""Bounded WM-08 regression, fake WM only; no display or input is accessed."""
import json
from unittest.mock import patch
from luda.desktop import Desktop
from luda.interaction import InteractionMixin
from luda.timing import elapsed_time
from luda.common import DesktopError

class Driver(InteractionMixin):
 def __init__(self):
  self.workspace=0
  self.windows={'sticky':{'window_id':'sticky','xid':10,'bounds':{'x':0,'y':0,'width':100,'height':100},'active':True,'workspace':-1}}
  self.snapshots={'before':{'time':elapsed_time(),'native':(100,100),'image':(100,100),'signature':self.signature(list(self.windows.values())),'topology':{'generation':1}}}
 def signature(self,windows):return Desktop.signature(self,windows)
 def target_window(self,*_):return self.windows['sticky']
 def workspaces(self):return [{'workspace':i,'active':i==self.workspace} for i in (0,1)]
 def display(self):return self
 root=1
 def geometry(self,_):return {'width':100,'height':100}
 def topology(self):return {'generation':1}
 def surface_at(self,*_):return 10
 def root_surface(self,_):return 10

def main():
 driver=Driver()
 def dispatch(argv,**_):
  assert argv==['wmctrl','-s','1'];driver.workspace=1;return b''
 with patch('luda.interaction.run',side_effect=dispatch):result=driver.switch_workspace(1)
 try:
  point=driver._interaction_point('sticky','before',20,20)
  stale={'accepted':True,'point':point}
 except DesktopError as exc:stale={'accepted':False,'code':exc.code}
 print(json.dumps({'requirement':'WM-08','backend':'deterministic fake WM, no GUI input','switch':result,'old_screenshot':stale,'retained':list(driver.snapshots)},indent=2))

if __name__=='__main__':main()
