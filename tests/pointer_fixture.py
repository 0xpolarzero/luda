"""Independent GTK pointer event oracle."""
import gi,json,sys
from pathlib import Path
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,Gdk,GLib
out=Path(sys.argv[1]);state={'presses':[],'releases':[],'scrolls':[]}
window=Gtk.Window(title='Luda pointer oracle');window.set_default_size(500,300)
area=Gtk.DrawingArea();area.add_events(Gdk.EventMask.BUTTON_PRESS_MASK|Gdk.EventMask.BUTTON_RELEASE_MASK|Gdk.EventMask.SCROLL_MASK);window.add(area)
def press(widget,event):
 if event.type==Gdk.EventType.BUTTON_PRESS:state['presses'].append(event.button)
 return True
def release(widget,event):state['releases'].append(event.button);return True
def scroll(widget,event):state['scrolls'].append(str(event.direction));return True
area.connect('button-press-event',press);area.connect('button-release-event',release);area.connect('scroll-event',scroll)
def save():
 (out/'state.tmp').write_text(json.dumps(state));(out/'state.tmp').replace(out/'state.json');return True
GLib.timeout_add(10,save);window.connect('destroy',Gtk.main_quit);window.show_all();Gtk.main()
