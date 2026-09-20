"""Real private XFCE/D-Bus/Xvfb lifecycle; never restarts the user's display/bus."""
import argparse
import ast
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from luda.desktop import Desktop
from luda.common import DesktopError
from luda.session import discover
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/accessibility-lifecycle'

def gdbus(destination,path,method,*args):
 r=subprocess.run(['gdbus','call','--session','--dest',destination,'--object-path',path,'--method',method,*map(str,args)],capture_output=True,text=True,timeout=4,check=True)
 return r.stdout.strip()
def address():return ast.literal_eval(gdbus('org.a11y.Bus','/org/a11y/bus','org.a11y.Bus.GetAddress'))[0]
def service_pid(name):
 raw=gdbus('org.freedesktop.DBus','/org/freedesktop/DBus','org.freedesktop.DBus.GetConnectionUnixProcessID',name)
 return int(raw.removeprefix('(uint32 ').removesuffix(',)'))
def children(pid):
 result=[]
 for f in Path('/proc').iterdir():
  if not f.name.isdigit():continue
  try:
   fields=(f/'stat').read_text().rsplit(')',1)[1].split()
   if int(fields[1])==pid:result.append(int(f.name))
  except (OSError,ValueError):pass
 return result

def child(out,restart):
 records=[];wm=None;fixture=None;d=None
 def record(name,okay,detail=None):
  records.append({'case':name,'passed':bool(okay),'detail':detail});print(json.dumps(records[-1]),flush=True)
 def launch_fixture():
  appout=out/('app-'+uuid.uuid4().hex);appout.mkdir()
  app=subprocess.Popen(['/usr/bin/python3',str(ROOT/'tests/fixture.py'),str(appout)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  deadline=time.monotonic()+6
  while time.monotonic()<deadline:
   try:found=next((x for x in d.list_windows() if x['pid']==app.pid),None)
   except DesktopError:found=None
   if found:return app,appout,found
   if app.poll() is not None:raise RuntimeError('fixture exited')
   time.sleep(.05)
  app.terminate();app.wait(timeout=2);raise RuntimeError('fixture window timeout')
 def accessible(window,timeout=8):
  deadline=time.monotonic()+timeout;errors=[]
  while time.monotonic()<deadline:
   try:
    tree=d.inspect(window['window_id'])
    if tree['available'] and any(n['name']=='Contract text' for n in tree['nodes']):return tree,{'codes':sorted(set(errors)),'failed_attempts':len(errors)}
   except DesktopError as e:errors.append(e.code)
   time.sleep(.5)
  return None,{'codes':sorted(set(errors)),'failed_attempts':len(errors)}
 try:
  log=(out/'xfce.log').open('w')
  wm=subprocess.Popen(['xfce4-session','--disable-tcp'],stdout=log,stderr=log)
  deadline=time.monotonic()+8
  while time.monotonic()<deadline:
   if wm.poll() is not None:raise RuntimeError('XFCE exited: '+(out/'xfce.log').read_text()[-1000:])
   if subprocess.run(['wmctrl','-l'],capture_output=True).returncode==0:break
   time.sleep(.05)
  current=discover(os.getuid(),wm.pid)
  record('real-xfce-session-discovery',current['DISPLAY']==os.environ['DISPLAY'] and current['DBUS_SESSION_BUS_ADDRESS']==os.environ['DBUS_SESSION_BUS_ADDRESS'])
  launched=subprocess.run([str(ROOT/'.venv/bin/luda-session'),'--session-pid',str(wm.pid),'--',sys.executable,'-c','import os,json;print(json.dumps({k:os.environ.get(k) for k in ("DISPLAY","DBUS_SESSION_BUS_ADDRESS")}))'],capture_output=True,text=True,timeout=4,check=True)
  launched_env=json.loads(launched.stdout)
  record('real-launcher-attaches-explicit-session',launched_env['DISPLAY']==current['DISPLAY'] and launched_env['DBUS_SESSION_BUS_ADDRESS']==current['DBUS_SESSION_BUS_ADDRESS'])
  (out/'session.json').write_text(json.dumps({'pid':wm.pid,'display':current['DISPLAY'],'bus':current['DBUS_SESSION_BUS_ADDRESS']}))
  d=Desktop();fixture,appout,window=launch_fixture();tree,errors=accessible(window)
  record('initial-accessibility',tree is not None,errors)
  if tree is None:return records
  d.activate(window['window_id']);editor=next(n for n in tree['nodes'] if n['name']=='Contract text')
  result=d.element(editor['element_id'],'set',text='lifecycle\n日本語\n');time.sleep(.1)
  record('initial-independent-write',result['exact_match'] and json.loads((appout/'state.json').read_text())['text']=='lifecycle\n日本語\n')
  if restart:
   old_address=address();launcher=service_pid('org.a11y.Bus')
   bus_children=children(launcher)
   record('private-accessibility-bus-identified',bool(bus_children),{'launcher':launcher,'children':bus_children})
   # These PIDs are obtained from this private D-Bus owner and its actual children.
   # No process-name kill, global bus address, or shared :1 process is involved.
   for pid in bus_children:
    try:os.kill(pid,signal.SIGTERM)
    except ProcessLookupError:pass
   try:os.kill(launcher,signal.SIGTERM)
   except ProcessLookupError:pass
   time.sleep(.2)
   new_address=address()
   record('actual-accessibility-bus-restarted',new_address!=old_address,{'address_changed':new_address!=old_address})
   same,errors=accessible(window)
   record('existing-provider-reconnected',same is not None,errors)
   # Accessibility loss does not remove the actual X11 application. Verify the
   # screenshot/pointer/clipboard path against the still-running fixture buffer.
   d.activate(window['window_id']);shot=d.observe();bounds=editor['bounds']
   px=(bounds['x']+bounds['width']/2)*shot['image_size']['width']/shot['desktop_size']['width']
   py=(bounds['y']+bounds['height']/2)*shot['image_size']['height']/shot['desktop_size']['height']
   d.pointer(window['window_id'],shot['snapshot_id'],px,py);d.key(window['window_id'],'ctrl+a')
   d.paste(window['window_id'],'X11 after bus loss\n','ctrl_v');time.sleep(.15)
   record('x11-fallback-survives-accessibility-loss',json.loads((appout/'state.json').read_text())['text']=='X11 after bus loss\n')
   fixture.terminate();fixture.wait(timeout=3);fixture=None
   try:d.activate(window['window_id'])
   except DesktopError as e:record('old-window-refused-after-app-close',e.code=='STALE_TARGET',e.code)
   else:record('old-window-refused-after-app-close',False)
   fixture,appout,window=launch_fixture();fresh,errors=accessible(window)
   record('same-desktop-new-provider-after-bus-restart',fresh is not None,errors)
   if fresh:
    d.activate(window['window_id']);editor=next(n for n in fresh['nodes'] if n['name']=='Contract text')
    result=d.element(editor['element_id'],'set',text='after restart\n');time.sleep(.1)
    record('independent-write-after-restart',result['exact_match'] and json.loads((appout/'state.json').read_text())['text']=='after restart\n')
 except Exception as exc:record('unexpected-failure',False,{'type':type(exc).__name__,'message':str(exc)})
 finally:
  if fixture and fixture.poll() is None:fixture.terminate();fixture.wait(timeout=3)
  if d:d.close()
  if wm and wm.poll() is None:
   wm.terminate()
   try:wm.wait(timeout=4)
   except subprocess.TimeoutExpired:wm.kill();wm.wait(timeout=2)
  (out/'results.json').write_text(json.dumps(records,indent=2))
 return records

def kill_owned(token):
 matched=[]
 needle=('LUDA_LIFECYCLE_TEST_TOKEN='+token).encode()
 for f in Path('/proc').iterdir():
  if not f.name.isdigit():continue
  try:
   if f.stat().st_uid==os.getuid() and needle in (f/'environ').read_bytes().split(b'\0'):
    matched.append(int(f.name))
  except OSError:pass
 for pid in matched:
  try:os.kill(pid,signal.SIGTERM)
  except ProcessLookupError:pass
 return matched

def main():
 OUT.mkdir(parents=True,exist_ok=True)
 parser=argparse.ArgumentParser();parser.add_argument('--child',type=Path);parser.add_argument('--restart',action='store_true');args=parser.parse_args()
 if args.child:
  rows=child(args.child,args.restart);raise SystemExit(0 if all(x['passed'] for x in rows) else 1)
 rows=[];sessions=[]
 for iteration in range(2):
  out=OUT/str(iteration);out.mkdir(exist_ok=True)
  for old in ('results.json','session.json'):(out/old).unlink(missing_ok=True)
  with tempfile.TemporaryDirectory(prefix='luda-private-session-') as directory:
   base=Path(directory);config=base/'config';config.mkdir();runtime=base/'runtime';runtime.mkdir(mode=0o700)
   channel=config/'xfce4/xfconf/xfce-perchannel-xml';channel.mkdir(parents=True)
   (channel/'xfce4-session.xml').write_text('''<?xml version="1.0"?><channel name="xfce4-session" version="1.0"><property name="general" type="empty"><property name="FailsafeSessionName" type="string" value="Failsafe"/><property name="SaveOnExit" type="bool" value="false"/></property><property name="startup" type="empty"><property name="ssh-agent" type="empty"><property name="enabled" type="bool" value="false"/></property><property name="gpg-agent" type="empty"><property name="enabled" type="bool" value="false"/></property></property><property name="sessions" type="empty"><property name="Failsafe" type="empty"><property name="IsFailsafe" type="bool" value="true"/><property name="Count" type="int" value="1"/><property name="Client0_Command" type="array"><value type="string" value="xfwm4"/></property><property name="Client0_Priority" type="int" value="15"/></property></property></channel>''')
   authority=base/'authority';authority.touch(mode=0o600)
   token=uuid.uuid4().hex
   rd,wr=os.pipe();xvfb=subprocess.Popen(['Xvfb','-displayfd',str(wr),'-screen','0','900x700x24','-nolisten','tcp','-ac'],pass_fds=(wr,),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);os.close(wr)
   process=None
   try:
    if not select.select([rd],[],[],5)[0]:raise RuntimeError('Xvfb startup timeout')
    number=os.read(rd,32).decode().strip();os.close(rd)
    env=dict(os.environ,DISPLAY=':'+number,XAUTHORITY=str(authority),ICEAUTHORITY=str(base/'iceauthority'),XDG_RUNTIME_DIR=str(runtime),XDG_CONFIG_HOME=str(config),XDG_CONFIG_DIRS=str(config),XDG_CACHE_HOME=str(base/'cache'),XDG_DATA_HOME=str(base/'data'),GSETTINGS_BACKEND='memory',GNUPGHOME=str(base/'gnupg'),LUDA_LIFECYCLE_TEST_TOKEN=token)
    env.pop('SESSION_MANAGER',None);env.pop('DBUS_SESSION_BUS_ADDRESS',None)
    command=['dbus-run-session','--',sys.executable,str(Path(__file__).resolve()),'--child',str(out)]
    if iteration==0:command.append('--restart')
    with (out/'run.log').open('w') as log:
     process=subprocess.Popen(command,env=env,stdout=log,stderr=log,start_new_session=True)
     process.wait(timeout=45)
    if (out/'results.json').exists():rows.extend(json.loads((out/'results.json').read_text()))
    if (out/'session.json').exists():sessions.append(json.loads((out/'session.json').read_text()))
   finally:
    if process:
     try:os.killpg(process.pid,signal.SIGTERM)
     except ProcessLookupError:pass
     if process.poll() is None:process.wait(timeout=4)
    killed=kill_owned(token)
    if xvfb.poll() is None:xvfb.terminate();xvfb.wait(timeout=3)
    (out/'cleanup.json').write_text(json.dumps({'owned_processes_terminated':killed}))
  if sessions:
   try:discover(os.getuid(),sessions[-1]['pid'])
   except SystemExit:rows.append({'case':'terminated-real-session-refused','passed':True})
   else:rows.append({'case':'terminated-real-session-refused','passed':False})
 if len(sessions)==2:rows.append({'case':'new-real-session-has-new-bus-and-pid','passed':sessions[0]['pid']!=sessions[1]['pid'] and sessions[0]['bus']!=sessions[1]['bus']})
 (OUT/'results.json').write_text(json.dumps(rows,indent=2));print(json.dumps(rows,indent=2));raise SystemExit(0 if rows and all(r['passed'] for r in rows) else 1)
if __name__=='__main__':main()
