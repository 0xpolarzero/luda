"""Owned rendered-text oracle with Pango ink geometry independent of OCR."""
import gi,json,sys
from pathlib import Path
gi.require_version('Gtk','3.0');gi.require_version('PangoCairo','1.0')
from gi.repository import Gtk,GLib,Pango,PangoCairo
out=Path(sys.argv[1]);window=Gtk.Window(title='Luda OCR owned canvas');window.set_default_size(800,260)
area=Gtk.DrawingArea();window.add(area);changed=False

def draw(widget,cr):
    cr.set_source_rgb(1,1,1);cr.paint();cr.set_source_rgb(0,0,0)
    origin=widget.get_window().get_origin();boxes=[]
    for x,text in [(50,'LUDA'),(260,'ORBIT'),(490,'4271')]:
        actual='CHANGED' if changed else text
        layout=PangoCairo.create_layout(cr);layout.set_font_description(Pango.FontDescription('DejaVu Sans 36'));layout.set_text(actual,-1)
        ink,_=layout.get_pixel_extents();cr.move_to(x,80);PangoCairo.show_layout(cr,layout)
        boxes.append({'text':actual,'bounds':{'x':origin.x+x+ink.x,'y':origin.y+80+ink.y,'width':ink.width,'height':ink.height}})
    (out/'oracle.tmp').write_text(json.dumps({'changed':changed,'words':boxes}));(out/'oracle.tmp').replace(out/'oracle.json')
    return False

def update():
    global changed
    if not changed and (out/'change').exists():changed=True;area.queue_draw()
    return True
area.connect('draw',draw);window.connect('destroy',Gtk.main_quit);GLib.timeout_add(20,update);window.show_all();Gtk.main()
