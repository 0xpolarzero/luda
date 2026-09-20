"""Owned GTK capture oracle switches visible color after an explicit test gate."""

import gi, json, sys
from pathlib import Path

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib

out = Path(sys.argv[1])
window = Gtk.Window(title="Luda recording owned colors")
window.set_default_size(600, 400)
area = Gtk.DrawingArea()
window.add(area)
green = False


def draw(widget, cr):
    cr.set_source_rgb(0, 1, 0) if green else cr.set_source_rgb(1, 0, 0)
    cr.paint()
    (out / "state.json").write_text(json.dumps({"green": green}))
    return False


def tick():
    global green
    if (out / "green").exists() and not green:
        green = True
        area.queue_draw()
    return True


area.connect("draw", draw)
GLib.timeout_add(30, tick)
window.connect("destroy", Gtk.main_quit)
window.show_all()
Gtk.main()
