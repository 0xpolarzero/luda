"""Owned GTK geometry history; private ordinary-UID Xvfb/D-Bus only."""
import json,os,signal,subprocess,time,sys,tempfile
from pathlib import Path
from luda.desktop import Desktop
from luda.common import DesktopError
from live_window_geometry import FIXTURE,oracle

APP=FIXTURE.replace("w.connect('destroy',Gtk.main_quit);w.show_all();Gtk.main()",'''import signal
from gi.repository import GLib
def change_hints():
 g.min_width=340;g.min_height=220
 w.set_geometry_hints(None,g,Gdk.WindowHints.MIN_SIZE|Gdk.WindowHints.BASE_SIZE|Gdk.WindowHints.RESIZE_INC)
 return True
GLib.unix_signal_add(GLib.PRIORITY_DEFAULT,signal.SIGUSR1,change_hints)
w.connect('destroy',Gtk.main_quit);w.show_all();Gtk.main()''')

def main():
 assert os.getuid()!=0 and os.environ.get('LUDA_ISOLATED_TEST_DISPLAY')=='1'
 output=Path(os.environ.get('LUDA_GEOMETRY_OUTPUT',str(Path(__file__).resolve().parents[1]/'artifacts/restore-comparison')));output.mkdir(parents=True,exist_ok=True)
 wm=subprocess.Popen(['xfwm4','--compositor=off'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 driver=None;apps=[];records=[]
 def record(name,result):records.append({'case':name,'result':result});(output/'results.json').write_text(json.dumps(records,indent=2)+'\n')
 try:
  time.sleep(.4);driver=Desktop()
  def launch():
   app=subprocess.Popen(['/usr/bin/python3','-c',APP]);apps.append(app);deadline=time.monotonic()+5
   while time.monotonic()<deadline:
    found=next((w for w in driver.list_windows() if w['pid']==app.pid),None)
    if found:return app,found
    time.sleep(.03)
   raise AssertionError('owned fixture missing')
  app,window=launch();wid=window['window_id'];xid=window['xid']
  def action(name,**args):
   with driver.transaction():return driver.manage_window(wid,name,**args)
  def comparison(result):return result['observed_geometry']['restore_comparison']
  action('move',x=100,y=120)
  result=action('resize',width=100,height=100)
  assert result['observed_geometry']['request_match']=='nonmatching'
  assert oracle(xid)['client_bounds']['width']>=300;record('minimum-constrained resize',result)
  before=oracle(xid)
  result=action('maximize');assert result['observed_geometry']['restore_reference']['status']=='captured'
  result=action('maximize');assert result['observed_geometry']['restore_reference']['status']=='captured'
  result=action('restore');actual=oracle(xid)
  assert comparison(result)['status']=='matched' and comparison(result)['prior_geometry']=={k:before[k] for k in ('client_bounds','frame_bounds')}
  assert all(result['observed_geometry'][k]==actual[k]==before[k] for k in ('client_bounds','frame_bounds'));record('repeated maximize and matched restore',result)
  action('maximize');os.kill(app.pid,signal.SIGUSR1)
  deadline=time.monotonic()+3
  while 'minimum size: 340 by 220' not in oracle(xid)['properties']:
   if time.monotonic()>deadline:raise AssertionError('independent new hints missing')
   time.sleep(.03)
  result=action('restore');assert comparison(result)['status']=='unknown';record('external hints change unknown',result)
  # Use a separate owned fixture: changing minimum hints left the first
  # fixture maximized under this XFWM; that observed unknown result is retained.
  app.terminate();app.wait(timeout=3)
  app,window=launch();wid=window['window_id'];xid=window['xid']
  action('maximize')
  subprocess.run(['wmctrl','-ir',str(xid),'-b','remove,maximized_vert,maximized_horz'],check=True)
  deadline=time.monotonic()+3
  while '_NET_WM_STATE_MAXIMIZED_' in oracle(xid)['properties']:
   if time.monotonic()>deadline:
    record('external unmaximize missing',oracle(xid));raise AssertionError('external unmaximize missing')
   time.sleep(.03)
  subprocess.run(['wmctrl','-ir',str(xid),'-e','0,170,190,-1,-1'],check=True)
  deadline=time.monotonic()+3
  while oracle(xid)['frame_bounds']['x']!=170:
   if time.monotonic()>deadline:raise AssertionError('external move missing')
   time.sleep(.03)
  result=action('restore');assert comparison(result)['status']=='unknown';record('external state and move unknown',result)
  action('maximize');action('workspace',workspace=0)
  result=action('restore');assert comparison(result)['reason']=='another_window_action';record('own state command invalidates even unchanged workspace',result)
  action('maximize');app.terminate();app.wait(timeout=3)
  replacement,newwindow=launch();newbefore=oracle(newwindow['xid'])
  try:action('restore');raise AssertionError('old identity accepted')
  except DesktopError as exc:assert exc.code=='STALE_TARGET' and exc.effect=='none'
  assert oracle(newwindow['xid'])==newbefore and wid not in driver.window_history.entries
  record('replacement never inherits geometry or receives restore',{'stale_effect':'none'})
  driver.close();assert not driver.window_history.entries;record('backend close clears references',{'entries':0})
  print(json.dumps({'passed':len(records),'scope':'observed history only; no forced geometry or continuous change tracking'}))
 finally:
  if driver:driver.close()
  for process in [*apps,wm]:
   if process.poll() is None:process.terminate()
   try:process.wait(timeout=3)
   except subprocess.TimeoutExpired:process.kill();process.wait()

def isolated():
 assert os.getuid()!=0
 root=Path(__file__).resolve().parents[1]
 sys.path.insert(0,str(root/'scripts'))
 from qualify import source_fingerprint
 source=source_fingerprint(root)
 output=Path(os.environ.get('LUDA_GEOMETRY_OUTPUT',str(root/'artifacts'/('restore-'+str(time.time_ns())))))
 assert not output.exists()
 with tempfile.TemporaryDirectory(prefix='luda-restore-session-') as private:
  env=dict(os.environ,LUDA_RESTORE_CHILD='1',LUDA_ISOLATED_TEST_DISPLAY='1',LUDA_GEOMETRY_OUTPUT=str(output),GSETTINGS_BACKEND='memory')
  for key in ('HOME','XDG_RUNTIME_DIR','XDG_CONFIG_HOME','XDG_DATA_HOME','XDG_CACHE_HOME'):
   path=Path(private)/key;path.mkdir(mode=0o700);env[key]=str(path)
  env['XDG_CONFIG_DIRS']=env['XDG_CONFIG_HOME']
  process=subprocess.Popen(['xvfb-run','-a','-s','-screen 0 1200x900x24 -nolisten tcp','dbus-run-session','--',sys.executable,__file__],env=env,start_new_session=True)
  try:code=process.wait(timeout=60)
  finally:
   try:os.killpg(process.pid,signal.SIGTERM)
   except ProcessLookupError:pass
   process.wait(timeout=3)
  after=source_fingerprint(root)
  output.mkdir(exist_ok=True)
  (output/'environment.json').write_text(json.dumps({'uid':os.getuid(),'source_before':source,'source_after':after,'source_unchanged':source==after,'returncode':code,'session':'private Xvfb/D-Bus/HOME/XDG'},indent=2)+'\n')
  assert source==after
  raise SystemExit(code)

if __name__=='__main__':
 if os.environ.get('LUDA_RESTORE_CHILD')=='1' or os.environ.get('LUDA_ISOLATED_TEST_DISPLAY')=='1':main()
 else:isolated()
