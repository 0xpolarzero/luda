"""Actual X11 popup identity probe. Run with the full live-test lease."""
import re
import subprocess
import time
from luda.desktop import Desktop

script='''import gi\ngi.require_version("Gtk","3.0")\nfrom gi.repository import Gtk\nw=Gtk.Window(title="Luda popup owner");w.set_default_size(320,200);w.show_all()\np=Gtk.Window(type=Gtk.WindowType.POPUP);p.set_transient_for(w);p.set_default_size(100,80);p.move(70,70);p.show_all()\nGtk.main()'''
p=subprocess.Popen(['/usr/bin/python3','-c',script]); d=Desktop()
try:
    deadline=time.monotonic()+5
    while time.monotonic()<deadline:
        owners=[w for w in d.list_windows() if w['pid']==p.pid]
        surfaces=d.display().popup_surfaces()
        matches=[s for s in surfaces if any(s['transient_for']==w['xid'] for w in owners)]
        if matches: break
        time.sleep(.1)
    assert len(matches)==1,(owners,surfaces)
    popup=matches[0]
    assert popup['bounds']['width']==100 and popup['bounds']['height']==80,popup
    assert popup['override_redirect'] is True
    owner=next(w for w in owners if w['xid']==popup['transient_for'])
    d.activate(owner['window_id'])
    snap=d.observe(333)
    observed=next(p for p in snap['popups'] if p['xid']==popup['xid'])
    nw,nh=snap['desktop_size']['width'],snap['desktop_size']['height']
    iw,ih=snap['image_size']['width'],snap['image_size']['height'];b=observed['bounds']
    columns=[i for i in range(iw) if b['x']<=i*nw//iw<b['x']+b['width']]
    rows=[i for i in range(ih) if b['y']<=i*nh//ih<b['y']+b['height']]
    expected={'x':columns[0],'y':rows[0],'width':len(columns),'height':len(rows)}
    assert observed['image_bounds']==expected,(observed,expected)
    ix=expected['x']+expected['width']//2;iy=expected['y']+expected['height']//2
    d.pointer_popup(owner['window_id'],observed['popup_id'],snap['snapshot_id'],ix,iy,kind='hover')
    actual={key:int(value) for key,value in re.findall(r'^(X|Y)=([0-9]+)$',subprocess.check_output(['xdotool','getmouselocation','--shell']).decode(),re.M)}
    assert actual=={'X':ix*nw//iw,'Y':iy*nh//ih},actual
    assert 'image_bounds' not in d.snapshots[snap['snapshot_id']]['popups'][0]
    print('PASS: actual GTK popup identity, scaled image bounds, and independent pointer-location oracle')
finally:
    p.terminate();p.wait(timeout=5);d.close()
