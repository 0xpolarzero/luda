"""Tooltip occlusion, attention focus and changing dialog defaults via public Desktop."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from luda.common import DesktopError
from luda.desktop import Desktop
ROOT=Path(__file__).resolve().parents[1]
def wait(fn,timeout=5):
 end=time.monotonic()+timeout
 while time.monotonic()<end:
  value=fn()
  if value:return value
  time.sleep(.03)
 raise AssertionError('Overlay oracle timeout')
def main():
 rows=[]
 with tempfile.TemporaryDirectory(prefix='luda-overlays-') as directory:
  state=Path(directory)/'state.json';app=subprocess.Popen(['/usr/bin/python3',str(ROOT/'tests/overlay_fixture.py'),str(state)])
  d=Desktop()
  try:
   owner=wait(lambda:next((w for w in d.list_windows() if w['pid']==app.pid and w['title']=='Luda overlay oracle'),None));wid=owner['window_id'];d.activate(wid)
   def oracle():return json.loads(state.read_text())
   wait(state.exists)
   def node(name,window=wid):return wait(lambda:next((n for n in d.inspect(window)['nodes'] if n['name']==name and n['role']=='push button'),None))
   def invoke(name,window=wid):return d.element(node(name,window)['element_id'],'invoke',action='click')
   proof=node('Proof action');snapshot=d.observe(2560);b=proof['bounds'];point=(b['x']+b['width']//2,b['y']+b['height']//2)
   # Native-sized screenshot avoids any coordinate conversion in this fixture.
   assert snapshot['image_size']==snapshot['desktop_size']
   invoke('Show overlapping help');wait(lambda:d.observe_popups())
   try:d.pointer(wid,snapshot['snapshot_id'],*point);raise AssertionError('Unobserved overlay accepted')
   except DesktopError as exc:assert exc.code=='OCCLUDED_TARGET',(exc.code,exc.message)
   assert oracle()['proof']==0 and oracle()['tooltip_presses']==0
   observed=d.observe(2560);assert any(p['owner_window_id']==wid for p in observed['popups'])
   d.key(wid,'Escape');wait(lambda:not d.observe_popups());fresh=d.observe(2560);d.pointer(wid,fresh['snapshot_id'],*point);wait(lambda:oracle()['proof']==1)
   rows.append('new-tooltip-occludes-old-point-with-no-click-and-explicit-dismiss-restores-action')
   before=d.observe(2560);invoke('Show attention window')
   notice=wait(lambda:next((w for w in d.list_windows() if w['pid']==app.pid and w['title']=='Luda attention notification' and w['active']),None))
   try:d.pointer(wid,before['snapshot_id'],*point);raise AssertionError('Focus loss accepted')
   except DesktopError as exc:assert exc.code in ('FOCUS_CHANGED','STALE_OBSERVATION'),exc.code
   assert oracle()['proof']==1
   invoke('Dismiss attention',notice['window_id']);wait(lambda:next(w for w in d.list_windows() if w['window_id']==wid)['active'])
   rows.append('attention-window-focus-change-refused-with-original-target-preserved')
   invoke('Show changing default');dialog=wait(lambda:next((w for w in d.list_windows() if w['pid']==app.pid and w['title']=='Luda changing default'),None))
   save=node('Save operation',dialog['window_id']);wait(lambda:oracle()['default']=='cancel')
   result=d.element(save['element_id'],'invoke',action='click');assert result['effect']=='dispatched'
   wait(lambda:oracle()['saved']==1);assert oracle()['cancelled']==0
   rows.append('explicit-save-identity-survives-dialog-default-changing-to-cancel')
  finally:
   d.close();app.terminate();app.wait(timeout=3)
 out=ROOT/'artifacts/overlays';out.mkdir(parents=True,exist_ok=True);evidence={'uid':os.getuid(),'passed':rows};(out/'results.json').write_text(json.dumps(evidence,indent=2)+'\n');print(json.dumps(evidence))
if __name__=='__main__':main()
