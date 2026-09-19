"""GTK context menu/submenu activation outside owner client bounds."""
import json
from pathlib import Path
import subprocess
import tempfile
import time
import threading
from luda.common import DesktopError, operation_scope
from luda.desktop import Desktop
from luda.interaction import InteractionMixin

Driver = Desktop

fixture='''import gi,sys\ngi.require_version("Gtk","3.0")\nfrom gi.repository import Gtk,Gdk,GLib\nfrom pathlib import Path\nw=Gtk.Window(title="Luda nested menu probe");w.set_default_size(300,200);w.move(150,150)\nb=Gtk.Button(label="Menu anchor");w.add(b)\nm=Gtk.Menu();item=Gtk.MenuItem(label="More actions");sub=Gtk.Menu();child=Gtk.MenuItem(label="Write proof");sub.append(child);item.set_submenu(sub);m.append(item);m.show_all()\nchild.connect("activate",lambda widget:Path(sys.argv[1]).write_text("nested action 日本語"))\ndef show():\n m.popup_at_widget(b,Gdk.Gravity.SOUTH_EAST,Gdk.Gravity.NORTH_WEST,None);return False\nw.show_all();GLib.timeout_add(500,show);Gtk.main()'''
with tempfile.TemporaryDirectory() as directory:
    output=Path(directory)/'action.txt';p=subprocess.Popen(['/usr/bin/python3','-c',fixture,str(output)])
    d=Driver()
    try:
        deadline=time.monotonic()+8
        while True:
            windows=d.list_windows();owner=next((w for w in windows if w['pid']==p.pid),None)
            popups=d.observe_popups(windows)
            owned=[s for s in popups if owner and s['owner_window_id']==owner['window_id']]
            if owned:break
            if time.monotonic()>deadline:raise AssertionError('menu did not appear')
            time.sleep(.1)
        with d.transaction():
            s=d.observe();menu=next(v for v in s['popups'] if v['pid']==p.pid)
            def point(surface,snapshot):
                b=surface['bounds'];return ((b['x']+b['width']/2)*snapshot['image_size']['width']/snapshot['desktop_size']['width'],(b['y']+b['height']/2)*snapshot['image_size']['height']/snapshot['desktop_size']['height'])
            x,y=point(menu,s)
            b=menu['bounds'];ob=owner['bounds']
            assert b['x']+b['width']/2>=ob['x']+ob['width'] or b['y']+b['height']/2>=ob['y']+ob['height'],'test must target outside owner'
            d.hover(owner['window_id'],s['snapshot_id'],x,y)
            deadline=time.monotonic()+4
            while len([v for v in d.observe_popups() if v['pid']==p.pid])<2:
                if time.monotonic()>deadline:raise AssertionError('submenu did not appear')
                time.sleep(.1)
            s=d.observe();submenu=next(v for v in s['popups'] if v['pid']==p.pid and v['xid']!=menu['xid'])
            x,y=point(submenu,s)
            cancelled=threading.Event();cancelled.set()
            try:
                with operation_scope(cancelled=cancelled):
                    d.pointer(owner['window_id'],s['snapshot_id'],x,y)
                raise AssertionError('cancelled operation dispatched')
            except DesktopError as exc:
                assert exc.code=='CANCELLED',exc.code
            assert not output.exists()
            pb=submenu['bounds']
            overlay_code='import gi;gi.require_version("Gtk","3.0");from gi.repository import Gtk;w=Gtk.Window(type=Gtk.WindowType.POPUP);w.set_default_size(%d,%d);w.move(%d,%d);w.show_all();Gtk.main()' % (pb['width'],pb['height'],pb['x'],pb['y'])
            overlay=subprocess.Popen(['/usr/bin/python3','-c',overlay_code])
            try:
                time.sleep(.3)
                try:
                    d.pointer(owner['window_id'],s['snapshot_id'],x,y)
                    raise AssertionError('occluded operation dispatched')
                except DesktopError as exc:
                    assert exc.code=='OCCLUDED_TARGET',exc.code
                assert not output.exists()
            finally:
                overlay.terminate();overlay.wait(timeout=5)
            result=d.pointer(owner['window_id'],s['snapshot_id'],x,y)
        deadline=time.monotonic()+3
        while not output.exists() and time.monotonic()<deadline:time.sleep(.05)
        assert output.read_text()=='nested action 日本語'
        try:
            d.pointer(owner['window_id'],s['snapshot_id'],x,y)
            raise AssertionError('vanished popup dispatched')
        except DesktopError as exc:
            assert exc.code=='STALE_OBSERVATION',exc.code
        print(json.dumps({'nested_menu':'callback wrote exact proof','tool_effect':result['effect'],'outside_owner':True,'cancelled_occluded_vanished':'rejected'}))
    finally:
        p.terminate();p.wait(timeout=5)
