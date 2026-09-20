"""Independent GTK key-event and text oracle for keyboard lifecycle tests."""
import gi
import json
import sys
from pathlib import Path
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,GLib
out=Path(sys.argv[1]);window=Gtk.Window(title='Luda keyboard oracle');window.set_default_size(600,350)
view=Gtk.TextView();window.add(view);events=[]
def event(widget,value):
    events.append({'keyval':value.keyval,'code':value.hardware_keycode,'state':int(value.state),'kind':str(value.type)})
    return False
view.connect('key-press-event',event);view.connect('key-release-event',event)
def save():
    buffer=view.get_buffer()
    (out/'state.tmp').write_text(json.dumps({'text':buffer.get_text(buffer.get_start_iter(),buffer.get_end_iter(),True),'events':events}))
    (out/'state.tmp').replace(out/'state.json');return True
GLib.timeout_add(10,save);window.connect('destroy',Gtk.main_quit);window.show_all();view.grab_focus();Gtk.main()
