"""Wait predicates against owned GTK state, with no fixed delay as the success oracle."""
import json
from pathlib import Path
import subprocess
import sys
import threading
import time

from luda.common import DesktopError, operation_scope
from luda.desktop import Desktop
from luda.waits import ConditionWaitsMixin

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/waits';OUT.mkdir(parents=True,exist_ok=True)
(OUT/'command.json').unlink(missing_ok=True)
(OUT/'state.json').unlink(missing_ok=True)
Driver=Desktop if hasattr(Desktop,'wait_condition') else type('WaitDriver',(ConditionWaitsMixin,Desktop),{})
d=Driver();results=[]
p=subprocess.Popen(['/usr/bin/python3',str(ROOT/'tests/wait_fixture.py'),str(OUT)])

def record(case,passed,**details):
    results.append({'case':case,'passed':bool(passed),**details})
    assert passed,results[-1]

def state():
    return json.loads((OUT/'state.json').read_text())

def command(identity,action):
    temporary=OUT/'command.tmp';temporary.write_text(json.dumps({'id':identity,'action':action}));temporary.replace(OUT/'command.json')

try:
    deadline=time.monotonic()+5
    while True:
        window=next((w for w in d.list_windows() if w['pid']==p.pid),None)
        if window and (OUT/'state.json').exists():break
        assert time.monotonic()<deadline,'Fixture failed to start'
        time.sleep(.04)
    wid=window['window_id'];d.activate(wid)
    command(time.time_ns(),'cycle')
    value=d.wait_condition('element_present',window_id=wid,name='Delayed control',states=['showing'],timeout=3)
    record('delayed-presence-independent',value['matched'] and state()['target_present'] and bool(value['elements']),result=value)
    value=d.wait_condition('element_absent',window_id=wid,name='Delayed control',timeout=3)
    record('delayed-absence-independent',value['matched'] and not state()['target_present'],result=value)
    before=state()['frame']
    value=d.wait_condition('pixels_stable',window_id=wid,stable_for=.2,timeout=.5)
    record('animation-does-not-match-stability',not value['matched'] and state()['frame']>before,result=value)
    command(time.time_ns(),'stop')
    value=d.wait_condition('pixels_stable',window_id=wid,stable_for=.2,timeout=3)
    record('stopped-animation-stability',value['matched'] and not state()['animating'],result=value)
    cancelled=threading.Event();timer=threading.Timer(.15,cancelled.set);timer.start()
    began=time.monotonic()
    try:
        with operation_scope(cancelled=cancelled):
            d.wait_condition('element_present',window_id=wid,name='Never created',timeout=3)
    except DesktopError as error:
        record('live-wait-cancellation',error.code=='CANCELLED' and time.monotonic()-began<1,code=error.code)
    else:record('live-wait-cancellation',False)
    finally:timer.cancel()
    value=d.wait_condition('element_absent',window_id=wid,name='Never created',timeout=1)
    record('wait-recovers-after-cancel',value['matched'] and not state()['target_present'])
finally:
    if p.poll() is None:p.terminate();p.wait(timeout=3)
    d.close()
    (OUT/'results.json').write_text(json.dumps(results,indent=2)+'\n')
    print(json.dumps(results,indent=2))
