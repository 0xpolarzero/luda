"""Actual X11 popup identity probe. Run with the full live-test lease."""
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
    print('PASS: actual GTK override-redirect popup observed with correct owner and 100x80 bounds')
finally:
    p.terminate();p.wait(timeout=5)
