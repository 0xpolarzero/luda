"""Run under flock /tmp/luda-live-tests.lock luda-session -- python ..."""
import json
import subprocess
import time
from luda.desktop import Desktop
from luda.interaction import InteractionMixin

class Driver(InteractionMixin, Desktop): pass

fixture = '''import gi\ngi.require_version("Gtk", "3.0")\nfrom gi.repository import Gtk\nw=Gtk.Window(title="Luda isolated interaction probe");w.set_default_size(360,220)\nw.connect("destroy",Gtk.main_quit);w.show_all();Gtk.main()'''
p = subprocess.Popen(['/usr/bin/python3','-c',fixture])
d = Driver(); results = []
try:
    deadline=time.monotonic()+8
    while True:
        w=next((w for w in d.list_windows() if w['pid']==p.pid),None)
        if w: break
        if time.monotonic()>deadline: raise RuntimeError('fixture did not appear')
        time.sleep(.1)
    with d.transaction():
        for action, kwargs in [('move',{'x':100,'y':120}),('resize',{'width':420,'height':240}),('maximize',{}),('restore',{}),('minimize',{}),('restore',{})]:
            result=d.manage_window(w['window_id'],action,**kwargs)
            results.append(result)
            assert result['effect']=='verified',result
        workspaces=d.workspaces(); active=next(v['workspace'] for v in workspaces if v['active'])
        assert d.manage_window(w['window_id'],'workspace',workspace=active)['effect']=='verified'
        assert d.switch_workspace(active)['effect']=='verified'
        results.append({'workspace':'existing current workspace assignment and switch verified'})
        d.activate(w['window_id']); snap=d.observe()
        current=next(v for v in snap['windows'] if v['window_id']==w['window_id'])
        b=current['bounds']; sx=snap['image_size']['width']/snap['desktop_size']['width'];sy=snap['image_size']['height']/snap['desktop_size']['height']
        result=d.hover(w['window_id'],snap['snapshot_id'],(b['x']+30)*sx,(b['y']+40)*sy)
        actual=subprocess.check_output(['xdotool','getmouselocation','--shell']).decode()
        assert f"X={b['x']+30}\n" in actual and f"Y={b['y']+40}\n" in actual,actual
        results.append({'hover':'pointer position independently verified'})
        assert isinstance(d.display().popup_surfaces(),list)
        assert d.display().transient_for(w['xid']) is None
        results.append({'popup_enumeration':'query completed; actual popup fixture not yet tested'})
        result=d.manage_window(w['window_id'],'close'); results.append(result)
        assert result['effect']=='verified',result
    print(json.dumps(results,indent=2))
finally:
    if p.poll() is None: p.terminate()
    p.wait(timeout=5)
