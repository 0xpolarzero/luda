"""Owned synthetic GTK fixture; oracle is written separately from client evidence."""
import json
import os
import random
from pathlib import Path
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk

rng = random.Random(os.urandom(32))
positions = [(rng.randrange(70, 160), 170), (rng.randrange(370, 470), 170)]
label = 'MEDIA CHECK ' + str(rng.randrange(10000, 99999))
texture = [(rng.random(), rng.random(), rng.random()) for _ in range(64)]
window = Gtk.Window(title='Owned Media Usability Fixture')
window.set_default_size(680, 420)
window.move(60, 60)
area = Gtk.DrawingArea()
window.add(area)

def draw(widget, cr):
    cr.set_source_rgb(0.96, 0.96, 0.96)
    cr.paint()
    cr.set_source_rgb(0.04, 0.04, 0.04)
    cr.select_font_face('DejaVu Sans')
    cr.set_font_size(27)
    cr.move_to(60, 95)
    cr.show_text(label)
    for x, y in positions:
        for n, color in enumerate(texture):
            cr.set_source_rgb(*color)
            cr.rectangle(x + (n % 8) * 7, y + (n // 8) * 7, 7, 7)
            cr.fill()
    _, root_x, root_y = area.get_window().get_origin()
    (Path(os.environ['LUDA_PROBE_DIR']) / 'oracle.json').write_text(json.dumps({
        'label': label, 'icons': [{'x':root_x+x,'y':root_y+y,'width':56,'height':56} for x,y in positions]
    }))

area.connect('draw', draw)
window.connect('destroy', Gtk.main_quit)
window.show_all()
Gtk.main()
