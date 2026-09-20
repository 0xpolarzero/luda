"""Owned pointer clicks/wheels: file oracle and independent X button mask."""
import json,os,signal,subprocess,sys,tempfile,threading,time
from pathlib import Path
from live_keyboard_guard import Oracle,wait,descendants
from luda.common import DesktopError,operation_scope
from luda.desktop import Desktop
from luda.pointer_input import click_button
ROOT=Path(__file__).resolve().parents[1]


def child():
 rows=[]
 with tempfile.TemporaryDirectory(prefix='luda-pointer-oracle-') as directory:
  out=Path(directory);wm=subprocess.Popen(['xfwm4','--compositor=off'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  app=None;d=None;oracle=None
  try:
   wait(lambda:subprocess.run(['wmctrl','-m'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0)
   app=subprocess.Popen(['/usr/bin/python3',str(ROOT/'tests/pointer_fixture.py'),directory],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
   d=Desktop();oracle=Oracle();found=[]
   wait(lambda:bool(found.extend(w for w in d.list_windows() if w['pid']==app.pid) or found))
   window=found[0];d.activate(window['window_id']);bounds=window['bounds']
   subprocess.run(['xdotool','mousemove',str(bounds['x']+bounds['width']//2),str(bounds['y']+bounds['height']//2)],check=True)
   wait(lambda:(out/'state.json').exists())
   def state():return json.loads((out/'state.json').read_text())
   click_button('1',3,window['xid']);wait(lambda:len(state()['releases'])==3)
   assert state()['presses']==[1,1,1] and state()['releases']==[1,1,1]
   click_button('4',4,window['xid']);click_button('6',3,window['xid']);wait(lambda:len(state()['scrolls'])==7)
   assert sum('UP' in value for value in state()['scrolls'])==4
   assert sum('LEFT' in value for value in state()['scrolls'])==3
   rows.append('triple-click-and-vertical-horizontal-wheel-exact-file-oracle')
   subprocess.run(['xdotool','mousedown','1'],check=True);held=oracle.buttons()
   try:
    try:click_button('1',1,window['xid']);raise AssertionError('held input accepted')
    except DesktopError as exc:assert exc.code=='INPUT_HELD'
    assert oracle.buttons()==held
   finally:subprocess.run(['xdotool','mouseup','1'],check=True)
   rows.append('held-button-refused-without-release')
   before=len(state()['presses'])
   controller=subprocess.Popen([sys.executable,'-c','from luda.pointer_input import click_button;click_button("1",20,'+str(window['xid'])+')'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
   try:
    wait(lambda:bool(oracle.buttons()&0x100))
    guards=descendants(controller.pid);assert len(guards)==1
    injectors=descendants(guards[0]);assert len(injectors)==1
    os.kill(injectors[0],signal.SIGSTOP);controller.kill();controller.wait(timeout=2)
    wait(lambda:not oracle.buttons(),3);wait(lambda:not Path('/proc',str(injectors[0])).exists(),3)
    time.sleep(.1);after=len(state()['presses']);time.sleep(.1)
    assert len(state()['presses'])==after and after>before
   finally:
    if controller.poll() is None:controller.kill();controller.wait(timeout=2)
   rows.append('controller-kill-stops-click-injector-before-owned-button-release')
   cancelled=threading.Event();errors=[]
   def wheel():
    try:
     with operation_scope(cancelled=cancelled):click_button('4',20,window['xid'])
    except DesktopError as exc:errors.append(exc)
   worker=threading.Thread(target=wheel);worker.start();wait(lambda:bool(oracle.buttons()&0x800))
   guards=[pid for pid in descendants(os.getpid()) if b'luda._keyboard_guard' in Path(f'/proc/{pid}/cmdline').read_bytes()]
   assert len(guards)==1;injectors=descendants(guards[0]);assert len(injectors)==1
   os.kill(injectors[0],signal.SIGSTOP);cancelled.set();worker.join(4)
   assert not worker.is_alive() and errors and errors[0].code=='CANCELLED' and errors[0].effect=='uncertain'
   wait(lambda:not oracle.buttons());time.sleep(.1);after=len(state()['scrolls']);time.sleep(.1)
   assert len(state()['scrolls'])==after
   rows.append('mid-wheel-cancellation-stops-repeat-before-release')
  finally:
   if oracle:oracle.close()
   if d:d.close()
   if app and app.poll() is None:app.terminate();app.wait(timeout=3)
   if wm.poll() is None:wm.terminate();wm.wait(timeout=3)
 print(json.dumps({'passed':rows},indent=2))


def main():
 if '--child' in sys.argv:return child()
 with tempfile.TemporaryDirectory(prefix='luda-private-pointer-session-') as directory:
  env=dict(os.environ)
  for key,name in (('XDG_CONFIG_HOME','config'),('XDG_DATA_HOME','data'),('XDG_CACHE_HOME','cache'),('XDG_RUNTIME_DIR','runtime')):
   path=Path(directory)/name;path.mkdir(mode=0o700);env[key]=str(path)
  env['XDG_CONFIG_DIRS']=env['XDG_CONFIG_HOME']
  result=subprocess.run(['xvfb-run','-a','-s','-screen 0 1000x750x24 -nolisten tcp','dbus-run-session','--',sys.executable,str(Path(__file__).resolve()),'--child'],env=env,timeout=30)
 raise SystemExit(result.returncode)

if __name__=='__main__':main()
