"""Two-window GTK drag-and-drop with an independent payload oracle."""
import json
from pathlib import Path
import subprocess
import tempfile
import time
from luda.desktop import Desktop
from luda.interaction import InteractionMixin

class Driver(Desktop, InteractionMixin): pass

fixture='''import gi,sys\ngi.require_version("Gtk","3.0")\nfrom gi.repository import Gtk,Gdk\nfrom pathlib import Path\ntargets=[Gtk.TargetEntry.new("UTF8_STRING",0,0)]\nw=Gtk.Window(title="Luda DND source");w.set_default_size(240,180)\ns=Gtk.EventBox();s.add(Gtk.Label(label="Drag payload"));w.add(s)\ns.drag_source_set(Gdk.ModifierType.BUTTON1_MASK,targets,Gdk.DragAction.COPY)\ns.connect("drag-data-get",lambda widget,context,data,info,time:data.set_text("luda drag payload 日本語",-1))\nv=Gtk.Window(title="Luda DND destination");v.set_default_size(240,180)\nd=Gtk.EventBox();d.add(Gtk.Label(label="Drop here"));v.add(d)\nd.drag_dest_set(Gtk.DestDefaults.ALL,targets,Gdk.DragAction.COPY)\ndef receive(widget,context,x,y,data,info,time):\n Path(sys.argv[1]).write_text(data.get_text());Gtk.drag_finish(context,True,False,time)\nd.connect("drag-data-received",receive)\nw.show_all();v.show_all();Gtk.main()'''
with tempfile.TemporaryDirectory() as directory:
    output=Path(directory)/'drop.txt'
    p=subprocess.Popen(['/usr/bin/python3','-c',fixture,str(output)])
    d=Driver()
    try:
        deadline=time.monotonic()+5
        while True:
            windows={w['title']:w for w in d.list_windows() if w['pid']==p.pid}
            if len(windows)==2: break
            if time.monotonic()>deadline: raise RuntimeError('fixture startup failed')
            time.sleep(.1)
        source=windows['Luda DND source']['window_id'];dest=windows['Luda DND destination']['window_id']
        with d.transaction():
            assert d.manage_window(source,'move',x=80,y=160)['effect']=='verified'
            assert d.manage_window(dest,'move',x=500,y=160)['effect']=='verified'
            d.activate(source);s=d.observe();bounds={w['window_id']:w['bounds'] for w in s['windows']}
            sx=s['image_size']['width']/s['desktop_size']['width'];sy=s['image_size']['height']/s['desktop_size']['height']
            a=bounds[source];b=bounds[dest]
            result=d.drag_between(source,dest,s['snapshot_id'],(a['x']+100)*sx,(a['y']+70)*sy,(b['x']+100)*sx,(b['y']+70)*sy)
        deadline=time.monotonic()+3
        while not output.exists() and time.monotonic()<deadline: time.sleep(.05)
        assert output.read_text()=='luda drag payload 日本語'
        assert result['effect']=='dispatched'
        print(json.dumps({'drag':'verified through GTK drag-data-received UTF-8 payload','tool_effect':result['effect']}))
    finally:
        p.terminate();p.wait(timeout=5)
