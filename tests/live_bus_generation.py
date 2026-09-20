"""Actual private bus replacement with provider/name/path reuse and a live window."""
import json
import os
from pathlib import Path
import signal
import subprocess
import time
from luda.desktop import Desktop
from luda.common import DesktopError
from live_accessibility_lifecycle import address,service_pid,children
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/bus-generation'

def main():
 if os.getuid()==0 or os.environ.get('LUDA_ISOLATED_TEST_DISPLAY')!='1':raise RuntimeError('Private ordinary-user matrix session required')
 OUT.mkdir(parents=True,exist_ok=True);records=[];app=None;d=None
 for name in ('attach.json','state.json'):(OUT/name).unlink(missing_ok=True)
 def record(case,passed,**details):
  row=dict(case=case,passed=bool(passed),**details);records.append(row);print(json.dumps(row),flush=True)
 def state():return json.loads((OUT/'state.json').read_text())
 def wait(predicate):
  deadline=time.monotonic()+5
  while time.monotonic()<deadline:
   try:
    value=predicate()
    if value:return value
   except (FileNotFoundError,DesktopError,StopIteration):pass
   time.sleep(.05)
  raise RuntimeError('Fixture readiness deadline')
 try:
  with (OUT/'provider.log').open('w') as log:
   app=subprocess.Popen(['/usr/bin/python3',str(ROOT/'tests/bus_generation_fixture.py'),str(OUT)],env=dict(os.environ,NO_AT_BRIDGE='1'),stdout=log,stderr=log)
   old_address=address();(OUT/'attach.json').write_text(json.dumps({'address':old_address}))
   d=Desktop();window=wait(lambda:next(w for w in d.list_windows() if w['pid']==app.pid));d.activate(window['window_id'])
   def observed():return next(n for n in d.inspect(window['window_id'])['nodes'] if n['name']=='Generation action')
   old=wait(observed);private=dict(d.elements[old['element_id']]['node']);initial=state()
   record('private-generation-not-exposed',not {'root_provider','root_bus_guid'}.intersection(old))
   d.element(old['element_id'],'invoke',action='click');wait(lambda:state()['actions']==1)
   record('initial-real-provider-action',state()['actions']==1)
   launcher=service_pid('org.a11y.Bus')
   for pid in children(launcher)+[launcher]:
    try:os.kill(pid,signal.SIGTERM)
    except ProcessLookupError:pass
   time.sleep(.2);replacement_address=address()
   (OUT/'attach.json').write_text(json.dumps({'address':replacement_address,'wanted':initial['provider']}))
   wait(lambda:state()['generation']==2)
   fresh=wait(observed);newprivate=d.elements[fresh['element_id']]['node'];newstate=state()
   record('same-live-target-on-new-bus',app.poll() is None and all(private[k]==newprivate[k] for k in ('pid','start','path','root_path','root_provider','role','name')) and initial['guid']!=newstate['guid'],socket_reused=old_address.split(',guid=')[0]==replacement_address.split(',guid=')[0])
   try:result=d.element(old['element_id'],'invoke',action='click')
   except DesktopError as error:result={'code':error.code,'effect':error.effect}
   time.sleep(.1)
   record('old-generation-handle-refused',result.get('code')=='STALE_TARGET' and result.get('effect')=='none' and state()['actions']==1,result=result,actual_actions=state()['actions'])
   d.element(fresh['element_id'],'invoke',action='click');wait(lambda:state()['actions']==2)
   record('fresh-generation-action-works',state()['actions']==2)
 except Exception as exc:record('harness-failure',False,error=type(exc).__name__,message=str(exc))
 finally:
  if d:d.close()
  if app and app.poll() is None:
   app.terminate();app.wait(timeout=3)
  (OUT/'results.json').write_text(json.dumps(records,indent=2)+'\n')
 return 0 if records and all(r['passed'] for r in records) else 1
if __name__=='__main__':raise SystemExit(main())
