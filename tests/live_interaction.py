"""Run under flock /tmp/luda-live-tests.lock luda-session -- python ..."""
import json
import re
import subprocess
import time
import tempfile
from pathlib import Path
from luda.desktop import Desktop
from luda.interaction import InteractionMixin

class Driver(Desktop, InteractionMixin): pass

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
        for action, kwargs in [('move',{'x':100,'y':120}),('resize',{'width':420,'height':240}),('maximize',{}),('restore',{}),('fullscreen',{}),('restore',{}),('minimize',{}),('restore',{})]:
            result=d.manage_window(w['window_id'],action,**kwargs)
            results.append(result)
            assert result['effect']=='verified',result
            if action=='fullscreen':
                assert '_NET_WM_STATE_FULLSCREEN' in subprocess.check_output(['xprop','-id',str(w['xid']),'_NET_WM_STATE']).decode()
            if action=='restore':
                assert '_NET_WM_STATE_FULLSCREEN' not in subprocess.check_output(['xprop','-id',str(w['xid']),'_NET_WM_STATE']).decode()
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
        peer=subprocess.Popen(['/usr/bin/python3','-c',fixture.replace('Luda isolated interaction probe','Luda raise peer')])
        pinned=None
        try:
            deadline=time.monotonic()+5
            while True:
                other=next((v for v in d.list_windows() if v['pid']==peer.pid),None)
                if other:break
                if time.monotonic()>deadline:raise AssertionError('raise peer did not appear')
                time.sleep(.05)
            pinned=subprocess.Popen(['/usr/bin/python3','-c',fixture.replace('Luda isolated interaction probe','Luda upper layer')])
            deadline=time.monotonic()+5
            while True:
                upper=next((v for v in d.list_windows() if v['pid']==pinned.pid),None)
                if upper:break
                if time.monotonic()>deadline:raise AssertionError('upper-layer fixture did not appear')
                time.sleep(.05)
            subprocess.check_call(['wmctrl','-ir',str(upper['xid']),'-b','add,above'])
            d.manage_window(other['window_id'],'move',x=100,y=120)
            subprocess.check_call(['xdotool','mousemove','0','0'])
            d.activate(other['window_id'])
            before_focus=int(subprocess.check_output(['xdotool','getactivewindow']))
            for _ in range(2):
                result=d.manage_window(w['window_id'],'raise')
                assert result['effect']=='verified',result
                # xwininfo lists immediate root children topmost-first. This
                # checks actual server stacking rather than WM's cached EWMH list.
                order=[int(v,16) for v in re.findall(r'^\s+(0x[0-9a-fA-F]+)',subprocess.check_output(['xwininfo','-root','-children']).decode(),re.MULTILINE)]
                first_frame=d.display().root_surface(w['xid']);peer_frame=d.display().root_surface(other['xid'])
                upper_frame=d.display().root_surface(upper['xid'])
                assert order.index(upper_frame)<order.index(first_frame)<order.index(peer_frame),order
                assert int(subprocess.check_output(['xdotool','getactivewindow']))==before_focus
            results.append({'raise':'stacking increased below the above-layer fixture, remained idempotent, and preserved independently observed focus'})
        finally:
            if pinned is not None:pinned.terminate();pinned.wait(timeout=5)
            peer.terminate();peer.wait(timeout=5)
        result=d.manage_window(w['window_id'],'close'); results.append(result)
        assert result['effect']=='verified',result
    with tempfile.TemporaryDirectory() as directory:
        proof=Path(directory)/'close.txt'
        blocked_code='import gi,sys;gi.require_version("Gtk","3.0");from gi.repository import Gtk;from pathlib import Path\nw=Gtk.Window(title="Luda unsaved close probe");w.set_default_size(300,180)\ndef close_requested(window,event):\n dialog=Gtk.MessageDialog(transient_for=w,modal=True,text="Synthetic unsaved changes",buttons=Gtk.ButtonsType.OK_CANCEL);dialog.connect("response",lambda *args:Path(sys.argv[1]).write_text("answered"));dialog.show_all();Path(sys.argv[1]).write_text("dialog-created");return True\nw.connect("delete-event",close_requested);w.show_all();Gtk.main()'
        blocked_app=subprocess.Popen(['/usr/bin/python3','-c',blocked_code,str(proof)])
        try:
            deadline=time.monotonic()+5
            while True:
                blocked=next((v for v in d.list_windows() if v['pid']==blocked_app.pid),None)
                if blocked:break
                if time.monotonic()>deadline:raise AssertionError('close fixture did not appear')
                time.sleep(.05)
            with d.transaction():result=d.manage_window(blocked['window_id'],'close')
            assert result['effect']=='dispatched' and result['outcome']=='blocked_by_dialog',result
            assert proof.read_text()=='dialog-created'
            assert any(v['window_id']==blocked['window_id'] for v in d.list_windows())
            assert result['dialog_window_ids']
            results.append({'close':'owned modal detected; owner stays open and dialog untouched'})
        finally:
            blocked_app.terminate();blocked_app.wait(timeout=5)
    print(json.dumps(results,indent=2))
finally:
    if p.poll() is None: p.terminate()
    p.wait(timeout=5)
