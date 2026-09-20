import sys,os,tempfile,json,subprocess,time,select
from pathlib import Path
if os.getuid()==0 or os.environ.get('LUDA_ISOLATED_TEST_DISPLAY')!='1':raise SystemExit('Use an ordinary account and a private disposable X11 display.')
ROOT=Path(__file__).resolve().parents[3];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'tests')]
from live_keyboard_guard import Oracle,wait
with tempfile.TemporaryDirectory(prefix='luda-virtual-review-') as directory:
 root=Path(directory);package=root/'luda';package.mkdir();(package/'__init__.py').write_text('__path__.append('+repr(str(ROOT/'src/luda'))+')\n')
 (package/'_browser_worker.py').write_text('''import importlib.util,sys,time
from pathlib import Path
spec=importlib.util.spec_from_file_location('luda._review_actual_worker', '''+repr(str(ROOT/'src/luda/_browser_worker.py'))+''');impl=importlib.util.module_from_spec(spec);spec.loader.exec_module(impl)
class ReviewWorker(impl.Worker):
 def dispatch(self,request):
  if request.get('op')=='review_key':
   self.page.set_content('<textarea id="target"></textarea>');self.page.locator('#target').focus()
   original=self.protocol.send
   class Pause:
    def send(inner,method,args):
     result=original(method,args)
     if args.get('type')=='keyDown':Path(request['marker']).write_text('actual CDP keydown completed');time.sleep(20)
     return result
   self.protocol=Pause();self.rich_key('v','KeyV',86,2)
  else:return super().dispatch(request)
impl.Worker=ReviewWorker;impl.main()
''')
 wm=subprocess.Popen(['xfwm4','--compositor=off'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);guard=None;oracle=Oracle();read,write=os.pipe()
 try:
  wait(lambda:subprocess.run(['wmctrl','-m'],capture_output=True).returncode==0)
  guard=subprocess.Popen([sys.executable,'-m','luda._browser_guard',str(root),str(write)],env=dict(os.environ,PYTHONPATH=str(root)),stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,pass_fds=(write,));os.close(write);write=None
  def send(value):guard.stdin.write(json.dumps(value).encode()+b'\n');guard.stdin.flush()
  send({'op':'open','url':'about:blank','executable':os.environ['LUDA_CHROMIUM_EXECUTABLE']})
  assert select.select([guard.stdout],[],[],8)[0];opened=json.loads(guard.stdout.readline());assert 'pid' in opened,opened
  marker=root/'keydown';send({'op':'review_key','marker':str(marker)})
  wait(marker.exists,5);before=sorted(oracle.pressed());guard.stdin.close();guard.wait(timeout=5);after=sorted(oracle.pressed());proof=os.read(read,10)
  print(json.dumps({'actual_browser_pid':opened['pid'],'actual_virtual_keydown_observed':marker.exists(),'physical_pressed_after_keydown':before,'physical_pressed_after_EOF':after,'guardian_exit':guard.returncode,'cleanup_proof':proof.decode(),'scope':'actual Chromium and Worker.rich_key; test-only pause after completed CDP keyDown and before keyUp'}))
  assert before==after==[] and proof==b'1'
 finally:
  if guard and guard.poll() is None:guard.kill();guard.wait(timeout=3)
  os.close(read)
  if write is not None:os.close(write)
  oracle.close();wm.terminate();wm.wait(timeout=3)
