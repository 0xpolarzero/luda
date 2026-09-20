"""Observe real GTK composition before conflicting public input operations.

Private Xvfb + D-Bus only. This is a qualification probe: unsafe cases fail.
"""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from luda.desktop import Desktop
from luda.common import DesktopError
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/ime';OUT.mkdir(parents=True,exist_ok=True)

def stop(p):
    if p is None:return
    try:os.killpg(p.pid,signal.SIGTERM)
    except ProcessLookupError:pass
    try:p.wait(timeout=3)
    except subprocess.TimeoutExpired:p.kill();p.wait(timeout=2)

def main():
    if os.environ.get('LUDA_ISOLATED_TEST_DISPLAY')!='1':raise SystemExit('Use isolated Xvfb + dbus-run-session only.')
    records=[]
    capability=None
    with tempfile.TemporaryDirectory(prefix='luda-ime-') as temp:
        os.environ.update(XDG_CONFIG_HOME=temp+'/config',XDG_CACHE_HOME=temp+'/cache',XDG_RUNTIME_DIR=temp,GTK_IM_MODULE='gtk-im-context-simple',NO_AT_BRIDGE='0')
        wm=subprocess.Popen(['xfwm4','--compositor=off'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
        try:
            deadline=time.monotonic()+8
            while subprocess.run(['wmctrl','-m'],capture_output=True).returncode:
                if time.monotonic()>deadline:raise RuntimeError('WM timeout')
                time.sleep(.1)
            for kind in ('entry','textview'):
                for operation in ('observe','focus','replace','insert','select','paste'):
                    app=None;d=Desktop();capability=d.doctor()['ime_composition'];oracle=Path(temp)/(kind+'-'+operation+'.json')
                    try:
                        app=subprocess.Popen(['/usr/bin/python3',str(ROOT/'tests/ime_fixture.py'),str(oracle),kind],stdout=subprocess.DEVNULL,stderr=(OUT/'fixture.log').open('a'),start_new_session=True)
                        deadline=time.monotonic()+6
                        while True:
                            w=next((w for w in d.list_windows() if w['pid']==app.pid),None)
                            if w:break
                            if time.monotonic()>deadline:raise RuntimeError('app timeout')
                            time.sleep(.05)
                        wid=w['window_id'];d.activate(wid)
                        tree=d.inspect(wid);field=next(n for n in tree['nodes'] if n['name']=='Composition field');eid=field['element_id']
                        d.element(eid,'focus');d.key(wid,'End')
                        before=d.element(eid,'read')
                        raw_before=json.loads(subprocess.check_output(['/usr/bin/python3',str(ROOT/'tests/ime_ax_probe.py'),str(app.pid)],text=True,timeout=4))
                        d.key(wid,'ctrl+shift+u')
                        for digit in ('3','0','6','b'):d.key(wid,digit)
                        time.sleep(.1)
                        pre=json.loads(oracle.read_text());ax=d.element(eid,'read')
                        raw=json.loads(subprocess.check_output(['/usr/bin/python3',str(ROOT/'tests/ime_ax_probe.py'),str(app.pid)],text=True,timeout=4))
                        response=None
                        try:
                            if operation=='observe':response=d.element(eid,'read')
                            elif operation=='focus':response=d.element(eid,'focus')
                            elif operation=='replace':response=d.type_text(eid,'AGENT',mode='replace')
                            elif operation=='insert':response=d.type_text(eid,'AGENT',mode='insert')
                            elif operation=='select':response=d.element(eid,'select',start_offset=0,end_offset=4)
                            else:response=d.paste(wid,'AGENT')
                        except DesktopError as exc:response={'error':exc.code,'effect':exc.effect}
                        time.sleep(.1);after=json.loads(oracle.read_text())
                        # Return is explicit fixture-owned completion for the
                        # oracle, not an implicit production recovery action.
                        d.key(wid,'Return');time.sleep(.1);completed=json.loads(oracle.read_text())
                        detected=bool(response.get('error') in ('IME_COMPOSITION_ACTIVE','COMPOSITION_UNAVAILABLE'))
                        records.append({'widget':kind,'operation':operation,'preedit_started':bool(pre['preedit']),
                            'before':before,'raw_before':raw_before,'ax_snapshot_unchanged':raw_before==raw,'during_ax':ax,'raw_ax':raw,'pre':pre,'response':response,'after':after,'completed':completed,
                            'guarded':detected,'preedit_preserved':pre['preedit']==after['preedit']})
                    finally:stop(app);d.close()
        finally:stop(wm)
    (OUT/'capability.json').write_text(json.dumps(capability,indent=2))
    (OUT/'results.json').write_text(json.dumps(records,ensure_ascii=False,indent=2))
    print(json.dumps([{'widget':r['widget'],'op':r['operation'],'active':r['preedit_started'],'preserved':r['preedit_preserved'],'guarded':r['guarded'],'effect':r['response'].get('effect')} for r in records]))
    return 0 if all(r['preedit_started'] and (r['operation']=='observe' or r['guarded']) for r in records) else 1
if __name__=='__main__':sys.exit(main())
