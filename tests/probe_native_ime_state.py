"""Read-only after fixture-owned preedit; results do not qualify EDIT-10."""
import json,os,subprocess,sys,time
from pathlib import Path
from luda.desktop import Desktop
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts/native-ime-state'
def until(fn,seconds=5):
 end=time.monotonic()+seconds
 while time.monotonic()<end:
  try:
   result=fn()
   if result:return result
  except (FileNotFoundError,json.JSONDecodeError):pass
  time.sleep(.05)
 raise RuntimeError('Probe readiness deadline')
def main():
 if os.getuid()==0 or os.environ.get('LUDA_ISOLATED_TEST_DISPLAY')!='1':raise RuntimeError('Private ordinary-user desktop only')
 OUT.mkdir(parents=True,exist_ok=True);rows=[]
 for version in ('3.0','4.0'):
  for kind in ('entry','textview'):
   path=OUT/(version+'-'+kind+'.json');log=(OUT/(version+'-'+kind+'.log')).open('w');env=dict(os.environ,GTK_IM_MODULE='gtk-im-context-simple',GTK_A11Y='atspi',NO_AT_BRIDGE='0');app=subprocess.Popen(['/usr/bin/python3',str(ROOT/'tests/ime_state_fixture.py'),str(path),version,kind],env=env,stdout=log,stderr=log);desktop=Desktop()
   try:
    def state():return json.loads(path.read_text())
    window=until(lambda:next((w for w in desktop.list_windows() if w['pid']==app.pid),None));wid=window['window_id'];desktop.activate(wid);desktop.key(wid,'End')
    def raw():return json.loads(subprocess.check_output(['/usr/bin/python3',str(ROOT/'tests/ime_state_ax_probe.py'),str(app.pid)],text=True,timeout=4))
    before=until(raw);desktop.key(wid,'ctrl+shift+u')
    for key in ('3','0','6','b'):desktop.key(wid,key)
    until(lambda:state()['preedit_nonempty'] and state()['late_attached']);pending=state();samples=[]
    # No input, focus, selection, reset, commit or cancellation after this point.
    for _ in range(3):samples.append(raw());time.sleep(.2)
    after=state();record={'gtk':version,'widget':kind,'before':before,'during':samples,'oracle_pending':pending,'oracle_after':after,'raw_snapshots_equal':all(s==before for s in samples),'pending_preserved':after['preedit_nonempty'] and after['preedit_characters']==pending['preedit_characters'] and after['committed']==pending['committed'],'late_listener_still_unknown':after['late_events']==0 and not after['late_known']}
    rows.append(record);(OUT/'observations.json').write_text(json.dumps(rows,indent=2));assert record['pending_preserved'],record
   finally:
    desktop.close();app.terminate();app.wait(timeout=3);log.close()
 print(json.dumps([{k:r[k] for k in ('gtk','widget','raw_snapshots_equal','pending_preserved','late_listener_still_unknown')} for r in rows]));return 0
if __name__=='__main__':raise SystemExit(main())
