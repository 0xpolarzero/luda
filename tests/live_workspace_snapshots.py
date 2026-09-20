"""Explicit workspace switch expires coordinates for a real owned sticky GTK window."""
import json,os,subprocess,time
from pathlib import Path
from luda.desktop import Desktop
from luda.common import DesktopError
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/workspace-snapshots'
APP='''import gi,json,sys
from pathlib import Path
gi.require_version('Gtk','3.0')
from gi.repository import Gtk
p=Path(sys.argv[1]);p.write_text('0');count=0
w=Gtk.Window(title='Luda owned sticky workspace probe');w.set_default_size(360,220)
b=Gtk.Button(label='Count input');w.add(b)
def click(*args):
 global count
 count+=1;p.write_text(str(count))
b.connect('clicked',click);w.connect('destroy',Gtk.main_quit)
w.show_all();w.stick();Gtk.main()
'''

def main():
 assert os.getuid()!=0 and os.environ.get('LUDA_ISOLATED_TEST_DISPLAY')=='1'
 OUT.mkdir(parents=True,exist_ok=True);counter=OUT/'clicks.txt';records=[]
 app=subprocess.Popen(['/usr/bin/python3','-c',APP,str(counter)]);d=None
 def record(case,**result):
  records.append({'case':case,**result});(OUT/'results.json').write_text(json.dumps(records,indent=2))
 def current_workspace():
  raw=subprocess.check_output(['xprop','-root','_NET_CURRENT_DESKTOP'],text=True)
  return int(raw.split('=')[-1].strip())
 try:
  d=Desktop();deadline=time.monotonic()+5
  while True:
   w=next((w for w in d.list_windows() if w['pid']==app.pid and w['workspace']==-1),None)
   if w:break
   assert time.monotonic()<deadline,'Sticky fixture did not appear';time.sleep(.03)
  with d.transaction():
   d.activate(w['window_id'])
   workspaces=d.workspaces();original=current_workspace()
   other=next(row['workspace'] for row in workspaces if row['workspace']!=original)
   snap=d.observe();bounds=w['bounds'];x=(bounds['x']+bounds['width']/2)*snap['image_size']['width']/snap['desktop_size']['width'];y=(bounds['y']+bounds['height']/2)*snap['image_size']['height']/snap['desktop_size']['height']
   result=d.switch_workspace(other);assert result['effect']=='verified' and result['screenshot_ids_invalidated']==1
   assert current_workspace()==other
   # XFWM may reset focus on switching even with a sticky client. Restore
   # only the observed target focus, so the original layout can match again.
   d.activate(w['window_id'])
   active=int(subprocess.check_output(['xdotool','getactivewindow'],text=True).strip())
   assert active==w['xid'],'Sticky focus changed; prerequisite not established'
   def refused_old(label):
    before=counter.read_text()
    try:d.pointer(w['window_id'],snap['snapshot_id'],x,y);raise AssertionError('Old snapshot accepted')
    except DesktopError as exc:assert exc.code=='STALE_OBSERVATION' and exc.effect=='none',exc
    assert counter.read_text()==before=='0'
    record(label,old_snapshot_refused=True,independent_clicks=0,active_workspace=current_workspace())
   refused_old('same sticky target reactivated after switch')
   result=d.switch_workspace(original);assert result['effect']=='verified' and current_workspace()==original
   d.activate(w['window_id'])
   refused_old('switch away and back does not revive snapshot')
   fresh=d.observe();assert fresh['snapshot_id']!=snap['snapshot_id']
   point=d.point(w['window_id'],fresh['snapshot_id'],x,y)
   record('fresh screenshot coordinates accepted',point=point,independent_clicks=int(counter.read_text()))
 finally:
  if d:d.close()
  if app.poll() is None:app.terminate()
  app.wait(timeout=3)

if __name__=='__main__':main()
