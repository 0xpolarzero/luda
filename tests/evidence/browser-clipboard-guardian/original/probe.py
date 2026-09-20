import sys,os,tempfile,json,subprocess,time,signal
from pathlib import Path
ROOT=Path('/workspace/luda-rich-clipboard');sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
from luda.desktop import Desktop
from live_keyboard_guard import Oracle,wait,descendants
with tempfile.TemporaryDirectory(prefix='luda-review-') as directory:
 root=Path(directory);package=root/'luda';package.mkdir();(package/'__init__.py').write_text('__path__.append('+repr(str(ROOT/'src/luda'))+')\n')
 (package/'_browser_worker.py').write_text('import sys,json\nfrom luda.keyboard import send_chord\nr=json.loads(sys.stdin.readline());send_chord("ctrl+shift+alt+F12",r["xid"])\n')
 wm=subprocess.Popen(['xfwm4','--compositor=off'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 fixture=guard=None;desktop=oracle=None
 try:
  wait(lambda:subprocess.run(['wmctrl','-m'],capture_output=True).returncode==0)
  fixture=subprocess.Popen(['/usr/bin/python3',str(ROOT/'tests/keyboard_fixture.py'),str(root)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
  desktop=Desktop();oracle=Oracle();windows=[]
  wait(lambda:bool(windows.extend(w for w in desktop.list_windows() if w['pid']==fixture.pid) or windows),5)
  window=windows[0];desktop.activate(window['window_id'])
  guard=subprocess.Popen([sys.executable,'-m','luda._browser_guard',str(root)],env=dict(os.environ,PYTHONPATH=str(root)),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
  guard.stdin.write(json.dumps({'xid':window['xid']}).encode()+b'\n');guard.stdin.flush()
  wait(lambda:oracle.code('Control_L') in oracle.pressed(),5)
  workers=descendants(guard.pid);keyboard_guards=descendants(workers[0]);injectors=descendants(keyboard_guards[-1]);assert injectors,(workers,keyboard_guards)
  os.kill(injectors[0],signal.SIGSTOP)
  before=sorted(oracle.pressed());guard.stdin.close();guard.wait(timeout=5);time.sleep(.15)
  print(json.dumps({'observed_held_before_eof':before,'held_after_browser_guard_exit':sorted(oracle.pressed()),'browser_guard_exit':guard.returncode,'scope':'actual browser guardian, test-only worker using actual keyboard guardian/native injector; injector stopped after real Control press'}))
 finally:
  if oracle:
   subprocess.run(['xdotool','keyup','ctrl','shift','alt','F12'],capture_output=True);oracle.close()
  if guard and guard.poll() is None:guard.kill();guard.wait(timeout=3)
  if desktop:desktop.close()
  if fixture:fixture.terminate();fixture.wait(timeout=3)
  wm.terminate();wm.wait(timeout=3)
