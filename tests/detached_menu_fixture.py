"""Native GTK3 tear-off menu, with independent persisted callback state."""
import json
from pathlib import Path
import sys
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,Gdk,GLib
out=Path(sys.argv[1]);out.mkdir(exist_ok=True)
window=Gtk.Window(title='Luda Tear-off Owner');window.set_default_size(350,160);window.move(100,120)
anchor=Gtk.Button(label='Open detachable actions');window.add(anchor)
menu=Gtk.Menu();menu.set_title('Luda Detached Actions');menu.attach_to_widget(anchor,None)
tear=Gtk.TearoffMenuItem();menu.append(tear)
proof=Gtk.MenuItem(label='Write detached proof');menu.append(proof)
wrong=Gtk.MenuItem(label='Wrong action');menu.append(wrong)
state={'proof':0,'wrong':0}
def save():
 state['detached']=menu.get_tearoff_state()
 (out/'state.tmp').write_text(json.dumps(state));(out/'state.tmp').replace(out/'state.json');return True
def activate(*_):
 state['proof']+=1;(out/'proof.txt').write_text('detached exact 日本語\n');save()
proof.connect('activate',activate)
wrong.connect('activate',lambda *_:state.update(wrong=state['wrong']+1))
anchor.connect('clicked',lambda *_:menu.popup_at_widget(anchor,Gdk.Gravity.SOUTH_EAST,Gdk.Gravity.NORTH_WEST,None))
menu.show_all();window.show_all();GLib.timeout_add(30,save);window.connect('destroy',Gtk.main_quit);Gtk.main()
