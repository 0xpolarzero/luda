import json,sys
from pathlib import Path
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,GLib,Gdk
out=Path(sys.argv[1]); name=sys.argv[2];state={'clicks':0,'menu':0}
w=Gtk.Window(title=name);w.set_default_size(300,240)
b=Gtk.Box(orientation=Gtk.Orientation.VERTICAL);w.add(b)
p=Gtk.Button(label='Click counter');b.pack_start(p,True,True,0)
e=Gtk.Entry();b.pack_start(e,True,True,0)
m=Gtk.Button(label='Open menu');b.pack_start(m,True,True,0)
menu=Gtk.Menu();item=Gtk.MenuItem(label='Menu counter');menu.append(item);menu.show_all()
def count(*_):state['clicks']+=1
p.connect('clicked',count)
def menu_count(*_):state['menu']+=1
item.connect('activate',menu_count)
m.connect('button-press-event',lambda widget,event:menu.popup_at_pointer(event))
def save():
 state['text']=e.get_text();state['menu_visible']=menu.get_visible();state['bounds']={}
 for key,widget in [('button',p),('entry',e),('menu_button',m)]:
  x,y=widget.translate_coordinates(w,0,0);_,wx,wy=w.get_window().get_origin();a=widget.get_allocation();state['bounds'][key]=[wx+x+a.width//2,wy+y+a.height//2]
 tmp=out.with_suffix('.tmp');tmp.write_text(json.dumps(state));tmp.replace(out);return True
w.show_all();GLib.timeout_add(30,save);Gtk.main()
