"""Owned GTK pattern with independent authored geometry, no matcher-derived oracle."""

import gi, json, sys
from pathlib import Path

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib

out = Path(sys.argv[1])
window = Gtk.Window(title="Luda owned image matching")
window.set_default_size(600, 300)
area = Gtk.DrawingArea()
window.add(area)
phase = 0


def draw(widget, cr):
    cr.set_source_rgb(1, 1, 1)
    cr.paint()
    cr.set_source_rgb(0.9, 0.1, 0.2)
    cr.rectangle(450, 180, 100, 80)
    cr.fill()
    origin = widget.get_window().get_origin()
    positions = (
        [(40, 40)] if phase == 0 else [(180, 40), (300, 90)] if phase == 1 else []
    )
    for x, y in positions:
        cr.set_source_rgb(0.9, 0.1, 0.2)
        cr.rectangle(x, y, 32, 32)
        cr.fill()
        cr.set_source_rgb(0.1, 0.2, 0.9)
        cr.rectangle(x + 3, y + 3, 9, 22)
        cr.fill()
        cr.set_source_rgb(0.1, 0.8, 0.2)
        cr.arc(x + 22, y + 12, 7, 0, 6.283185307)
        cr.fill()
        cr.set_source_rgb(0, 0, 0)
        cr.rectangle(x + 16, y + 25, 12, 4)
        cr.fill()
    value = {
        "phase": phase,
        "boxes": [
            {"x": origin.x + x, "y": origin.y + y, "width": 32, "height": 32}
            for x, y in positions
        ],
        "flat": {"x": origin.x + 500, "y": origin.y + 200, "width": 32, "height": 32},
    }
    (out / "oracle.tmp").write_text(json.dumps(value))
    (out / "oracle.tmp").replace(out / "oracle.json")
    return False


def update():
    global phase
    wanted = 2 if (out / "blank").exists() else 1 if (out / "change").exists() else 0
    if wanted != phase:
        phase = wanted
        area.queue_draw()
    return True


area.connect("draw", draw)
window.connect("destroy", Gtk.main_quit)
window.connect("configure-event", lambda *args: area.queue_draw() or False)
GLib.timeout_add(20, update)
window.show_all()
Gtk.main()
