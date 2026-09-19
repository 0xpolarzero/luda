"""Owned desktop-entry fixtures; run as desktop user under the live-test lease."""
import json
import os
from pathlib import Path
import signal
import tempfile
import time
import threading
from unittest.mock import patch
from luda.apps import launch_application,list_applications
from luda.common import DesktopError,operation_scope
from luda.desktop import Desktop

fixture='''import gi,json,os,sys\nfrom pathlib import Path\ngi.require_version("Gtk","3.0")\nfrom gi.repository import Gtk\nw=Gtk.Window(title="Luda launched application proof");w.set_default_size(220,120);w.show_all()\nPath(sys.argv[1]).write_text(json.dumps({"args":sys.argv[2:],"pid":os.getpid(),"sid":os.getsid(0),"uid":os.getuid(),"stdout":os.readlink("/proc/self/fd/1"),"stderr":os.readlink("/proc/self/fd/2"),"accessibility":os.environ.get("ACCESSIBILITY_ENABLED"),"qt_accessibility":os.environ.get("QT_LINUX_ACCESSIBILITY_ALWAYS_ON"),"no_at_bridge":os.environ.get("NO_AT_BRIDGE")}))\nGtk.main()'''
assert os.getuid()!=0,'This qualification must run as the ordinary desktop account'
with tempfile.TemporaryDirectory() as directory:
    base=Path(directory);entries=base/'applications';entries.mkdir();script=base/'fixture.py';script.write_text(fixture)
    for kind,field in [('files','%F'),('uris','%U'),('plain','')]:
        (entries/f'luda-proof-{kind}.desktop').write_text(f'[Desktop Entry]\nType=Application\nName=Luda Launch Proof {kind} 日本語\nExec=/usr/bin/python3 "{script}" "{base/kind}.json" {field}\nTerminal=false\n')
    (entries/'luda-proof-hidden.desktop').write_text('[Desktop Entry]\nType=Application\nName=Luda Launch Proof hidden\nExec=/bin/true\nNoDisplay=true\n')
    (entries/'luda-proof-broken.desktop').write_text('[Desktop Entry]\nType=Application\nName=Luda Launch Proof broken\n')
    file1=base/'日本語 space $(not-a-command);.txt';file1.write_text('one');file2=base/'percent% file.txt';file2.write_text('two')
    pids=[]
    try:
        with patch.dict(os.environ,{'XDG_DATA_HOME':str(base),'NO_AT_BRIDGE':'1'}):
            found=list_applications('Luda Launch Proof',limit=2)
            assert found['total_matches']==3 and found['truncated'],found
            for identity,values,expected in [
                ('files',[str(file1),str(file2)],[str(file1),str(file2)]),
                ('uris',['https://example.invalid/a?x=1&y=2',file1.as_uri()],['https://example.invalid/a?x=1&y=2',str(file1)]),
                ('plain',[],[])]:
                started=time.monotonic();result=launch_application(f'luda-proof-{identity}.desktop',values)
                assert time.monotonic()-started<3,'application stdout held helper open'
                pids.extend(result['spawned_pids']);assert result['effect']=='dispatched'
                output=base/f'{identity}.json';deadline=time.monotonic()+5
                while not output.exists() and time.monotonic()<deadline:time.sleep(.05)
                proof=json.loads(output.read_text());assert proof['args']==expected,proof
                assert proof['pid'] in result['spawned_pids'] and proof['sid']==proof['pid'],proof
                assert proof['uid']==os.getuid() and proof['stdout']=='/dev/null' and proof['stderr']=='/dev/null',proof
                assert proof['accessibility']=='1' and proof['qt_accessibility']=='1' and proof['no_at_bridge'] is None,proof
                windows=Desktop().list_windows();assert any(w['pid']==proof['pid'] for w in windows),windows
            cancelled=threading.Event();cancelled.set()
            try:
                with operation_scope(cancelled=cancelled):launch_application('luda-proof-plain.desktop')
                raise AssertionError('cancelled launch dispatched')
            except DesktopError as exc:assert exc.code=='CANCELLED',exc.code
            for pid in pids:os.kill(pid,0)
            for app,values,code in [('missing.desktop',[],'APPLICATION_NOT_FOUND'),('luda-proof-broken.desktop',[],'APPLICATION_NOT_FOUND'),('luda-proof-files.desktop',['https://example.invalid'],'UNSUPPORTED_INPUT'),('luda-proof-plain.desktop',[str(file1)],'UNSUPPORTED_INPUT'),('luda-proof-files.desktop',[str(base/'missing')],'FILE_NOT_FOUND')]:
                try:launch_application(app,values);raise AssertionError('invalid launch accepted')
                except DesktopError as exc:assert exc.code==code,(exc.code,code)
        print(json.dumps({'ordinary_uid':os.getuid(),'F_and_U_placeholders':'exact independent argv readback','application_windows':3,'stdio':'detached','sessions':'separate','accessibility_environment':'verified','missing_invalid_unsupported':'rejected','cancelled_launch':'existing fixtures unaffected'}))
    finally:
        for pid in pids:
            try:os.kill(pid,signal.SIGTERM)
            except ProcessLookupError:pass
