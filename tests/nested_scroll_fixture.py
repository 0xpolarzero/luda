"""Real nested GTK scrollers, with independent adjustment-value oracles."""
import json
import sys
from pathlib import Path
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

output = Path(sys.argv[1])
window = Gtk.Window(title='Luda nested scroll oracle')
window.set_default_size(640, 450)
outer = Gtk.ScrolledWindow()
outer.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.ALWAYS)
outer.get_accessible().set_name('Outer scrolling pane')
box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
box.pack_start(Gtk.Label(label='Nested scrolling fixture'), False, False, 0)
inner = Gtk.ScrolledWindow()
inner.set_policy(Gtk.PolicyType.ALWAYS, Gtk.PolicyType.ALWAYS)
inner.set_size_request(360, 200)
inner.set_halign(Gtk.Align.START)
inner.get_accessible().set_name('Inner scrolling pane')
canvas = Gtk.DrawingArea()
canvas.set_size_request(1200, 1000)
inner.add(canvas)
box.pack_start(inner, False, False, 0)
bottom = Gtk.Label(label='Outer content below the nested pane')
bottom.set_size_request(600, 1200)
box.pack_start(bottom, False, False, 0)
outer.add(box)
window.add(outer)

def persist():
    state = {name: {'value': a.get_value(), 'upper': a.get_upper(), 'page': a.get_page_size()}
             for name, a in [('inner_x', inner.get_hadjustment()), ('inner_y', inner.get_vadjustment()),
                             ('outer_y', outer.get_vadjustment())]}
    temporary = output.with_suffix('.tmp')
    temporary.write_text(json.dumps(state))
    temporary.replace(output)
    return True

GLib.timeout_add(20, persist)
window.connect('destroy', Gtk.main_quit)
window.show_all()
Gtk.main()
