"""GTK key/text oracle plus an action whose start and late completion are gated."""
import json
from pathlib import Path
import sys
import time
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,GLib
out=Path(sys.argv[1]);out.mkdir(exist_ok=True)
w=Gtk.Window(title='Luda Disconnect Oracle');w.set_default_size(600,350)
box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL);w.add(box)
view=Gtk.TextView();view.get_accessible().set_name('Disconnect text');box.pack_start(view,True,True,0)
button=Gtk.Button(label='Run gated action');box.pack_start(button,False,False,0)
state={'started':0,'completed':0,'key_presses':0}
def save():
 b=view.get_buffer();state['text']=b.get_text(b.get_start_iter(),b.get_end_iter(),True)
 (out/'state.tmp').write_text(json.dumps(state));(out/'state.tmp').replace(out/'state.json');return True
def pressed(*_):state['key_presses']+=1;save();return False
view.connect('key-press-event',pressed)
def action(*_):
 state['started']+=1;save();(out/'started').write_text(str(state['started']))
 deadline=time.monotonic()+8
 while not (out/'release').exists() and time.monotonic()<deadline:time.sleep(.005)
 state['completed']+=1;save()
button.connect('clicked',action);w.show_all();view.grab_focus();w.connect('destroy',Gtk.main_quit);GLib.timeout_add(10,save);Gtk.main()
