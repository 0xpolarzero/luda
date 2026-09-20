"""Real GTK backend requests under this test process's exhausted FD limit."""
import json
import os
from pathlib import Path
import resource
import subprocess
import sys
import time

from luda.common import DesktopError
from luda.desktop import Desktop

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/resource-limits'


def until(fn):
    end=time.monotonic()+8
    while time.monotonic()<end:
        value=fn()
        if value:return value
        time.sleep(.05)
    raise AssertionError('fixture did not become ready')


def exhausted(fn):
    old=resource.getrlimit(resource.RLIMIT_NOFILE);fds=[]
    began=time.monotonic()
    try:
        resource.setrlimit(resource.RLIMIT_NOFILE,(min(64,old[0]),old[1]))
        while True:
            try:fds.append(os.open('/dev/null',os.O_RDONLY))
            except OSError:break
        try:fn()
        except DesktopError as exc:return {'code':exc.code,'effect':exc.effect,'seconds':time.monotonic()-began}
        except Exception as exc:return {'exception':type(exc).__name__,'seconds':time.monotonic()-began}
        return {'unexpected_success':True}
    finally:
        for fd in fds:os.close(fd)
        resource.setrlimit(resource.RLIMIT_NOFILE,old)


def main():
    if os.geteuid()==0 or os.environ.get('LUDA_ISOLATED_TEST_DISPLAY')!='1':
        raise SystemExit('Requires ordinary user/private X11/D-Bus/XDG session.')
    OUT.mkdir(parents=True,exist_ok=True)
    app=subprocess.Popen(['/usr/bin/python3',str(ROOT/'tests/fixture.py'),str(OUT)],start_new_session=True)
    desktop=Desktop();records=[]
    def state():return json.loads((OUT/'state.json').read_text())
    def record(case,passed,**details):
        records.append({'case':case,'passed':bool(passed),**details});assert passed,records[-1]
    try:
        wid=until(lambda:next((w['window_id'] for w in desktop.list_windows() if w['pid']==app.pid),None))
        desktop.activate(wid)
        tree=until(lambda:desktop.inspect(wid))
        node=next(n for n in tree['nodes'] if n['name']=='Contract text')
        desktop.element(node['element_id'],'set',text='baseline 日本語\n')
        until(lambda:state()['text']=='baseline 日本語\n')
        desktop.observe()
        before=len(list(Path('/proc/self/fd').iterdir()))
        for name,fn in [('inspect',lambda:desktop.inspect(wid)),('capture',lambda:desktop.observe()),('mutation',lambda:desktop.element(node['element_id'],'set',text='must not arrive'))]:
            error=exhausted(fn)
            record(name+'-fd-exhaustion-typed-bounded',error.get('code')=='RESOURCE_UNAVAILABLE' and error['seconds']<3,**error)
            time.sleep(.3)
            record(name+'-no-delayed-write-or-fd-leak',state()['text']=='baseline 日本語\n' and len(list(Path('/proc/self/fd').iterdir()))==before)
        tree=desktop.inspect(wid)
        fresh=next(n for n in tree['nodes'] if n['name']=='Contract text')
        desktop.element(fresh['element_id'],'set',text='recovered 👩🏽‍💻\n')
        until(lambda:state()['text']=='recovered 👩🏽‍💻\n')
        record('restored-resources-new-request-recovers',bool(desktop.observe()['snapshot_id']))
    except Exception as exc:
        records.append({'case':'suite-completion','passed':False,'error_type':type(exc).__name__});raise
    finally:
        desktop.close();app.terminate()
        try:app.wait(timeout=3)
        except subprocess.TimeoutExpired:app.kill();app.wait(timeout=3)
        (OUT/'results.json').write_text(json.dumps(records,indent=2)+'\n');print(json.dumps(records),flush=True)

if __name__=='__main__':main()
