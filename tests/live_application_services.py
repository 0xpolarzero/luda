"""Terminal=true and private-bus singleton activation using owned fixtures."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from luda.apps import launch_application
from luda.desktop import Desktop
from luda.common import DesktopError,operation_scope


def await_file(path,predicate=lambda v:True):
    deadline=time.monotonic()+6
    while time.monotonic()<deadline:
        try:
            value=json.loads(path.read_text())
            if predicate(value):return value
        except (FileNotFoundError,json.JSONDecodeError):pass
        time.sleep(.05)
    raise AssertionError('fixture oracle timed out')


def worker(base):
    appid=(base/'application_id').read_text();pids=[]
    try:
        result=launch_application('luda-terminal-proof.desktop')
        terminal=await_file(base/'terminal.json');pids.append(terminal['pid'])
        assert result['effect']=='dispatched'
        windows=Desktop().list_windows()
        assert any(w['pid'] in result['spawned_pids'] for w in windows),'terminal window not observed'
        first=launch_application(appid+'.desktop')
        proof=await_file(base/'singleton.json');pids.append(proof['pid'])
        assert proof['activations']>=1,proof
        target=base/'日本語 singleton.txt';target.write_text('proof')
        second=launch_application(appid+'.desktop',[str(target)])
        later=await_file(base/'singleton.json',lambda v:bool(v['files']))
        assert later['pid']==proof['pid'] and later['files']==[target.as_uri()],later
        assert first['effect']==second['effect']=='dispatched'
        assert any(w['pid']==proof['pid'] for w in Desktop().list_windows())
        slow=base/'slow-request.txt';slow.write_text('proof')
        try:
            with operation_scope(timeout=.5):launch_application(appid+'.desktop',[str(slow)])
            raise AssertionError('slow activation should exceed deadline')
        except DesktopError as exc:assert exc.code=='TIMEOUT',exc.code
        after_timeout=await_file(base/'singleton.json',lambda v:v['files']==[slow.as_uri()])
        assert after_timeout['pid']==proof['pid'];os.kill(proof['pid'],0)
        print(json.dumps({'timed_out_activation':'singleton alive; delivered request observed','terminal_required':'executed in terminal','dbus_singleton':'same PID activated then opened exact file URI','first_spawn_hints':first['spawned_pids'],'second_spawn_hints':second['spawned_pids']}))
    finally:
        for pid in pids:
            try:os.kill(pid,signal.SIGTERM)
            except ProcessLookupError:pass


if len(sys.argv)>1:
    worker(Path(sys.argv[1]))
else:
    with tempfile.TemporaryDirectory() as directory:
        base=Path(directory);entries=base/'applications';entries.mkdir();services=base/'dbus-1'/'services';services.mkdir(parents=True)
        appid='org.luda.Probe'+uuid.uuid4().hex;(base/'application_id').write_text(appid)
        terminal_script=base/'terminal.py'
        terminal_script.write_text(f'import json,os,time\nfrom pathlib import Path\nPath({str(base/"terminal.json")!r}).write_text(json.dumps({{"pid":os.getpid()}}))\ntime.sleep(10)\n')
        (entries/'luda-terminal-proof.desktop').write_text(f'[Desktop Entry]\nType=Application\nName=Luda terminal proof\nExec=/usr/bin/python3 "{terminal_script}"\nTerminal=true\n')
        script=base/'singleton.py'
        script.write_text('''import gi,json,os,sys,time\nfrom pathlib import Path\ngi.require_version("Gtk","3.0")\nfrom gi.repository import Gtk,Gio\nclass App(Gtk.Application):\n def __init__(self):\n  super().__init__(application_id=APP_ID,flags=Gio.ApplicationFlags.HANDLES_OPEN);self.activations=0;self.files=[];self.window=None\n def record(self):\n  if self.window is None:self.window=Gtk.ApplicationWindow(application=self,title="Luda singleton proof");self.window.show_all()\n  Path(OUTPUT).write_text(json.dumps({"pid":os.getpid(),"activations":self.activations,"files":self.files}))\n def do_activate(self):self.activations+=1;self.record()\n def do_open(self,files,count,hint):\n  if any((f.get_basename() or "").startswith("slow-") for f in files):time.sleep(2)\n  self.files=[f.get_uri() for f in files];self.record()\nAPP_ID=APPID_VALUE\nOUTPUT=OUTPUT_VALUE\nApp().run(sys.argv)\n'''.replace('APPID_VALUE',repr(appid)).replace('OUTPUT_VALUE',repr(str(base/'singleton.json'))))
        (entries/(appid+'.desktop')).write_text(f'[Desktop Entry]\nType=Application\nName=Luda singleton proof\nExec=/usr/bin/python3 "{script}" %U\nDBusActivatable=true\nTerminal=false\n')
        (services/(appid+'.service')).write_text(f'[D-BUS Service]\nName={appid}\nExec=/usr/bin/python3 "{script}" --gapplication-service\n')
        subprocess.run(['dbus-run-session','--',sys.executable,__file__,str(base)],env={**os.environ,'XDG_DATA_HOME':str(base)},check=True,timeout=20)
