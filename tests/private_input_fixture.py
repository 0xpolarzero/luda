"""GTK application/file oracle for concurrent independent-input validation."""
import json
import sys
from pathlib import Path
import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Gdk', '3.0')
from gi.repository import Gdk, GLib, Gtk

out, title = Path(sys.argv[1]), sys.argv[2]
state = {'clicks': 0, 'menu_actions': 0, 'presses': 0, 'releases': 0, 'motions': 0, 'keys': []}
window = Gtk.Window(title=title)
window.set_default_size(420, 390)
box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
window.add(box)
entry = Gtk.Entry()
box.pack_start(entry, False, False, 0)
button = Gtk.Button(label='Count click')
box.pack_start(button, False, False, 0)
menu_button = Gtk.Button(label='Open menu')
box.pack_start(menu_button, False, False, 0)
area = Gtk.DrawingArea()
area.add_events(Gdk.EventMask.BUTTON_PRESS_MASK | Gdk.EventMask.BUTTON_RELEASE_MASK | Gdk.EventMask.POINTER_MOTION_MASK)
box.pack_start(area, True, True, 0)
menu = Gtk.Menu()
item = Gtk.MenuItem(label='Count menu action')
menu.append(item)
menu.show_all()
def increment(key):
    state[key] += 1
button.connect('clicked', lambda *_: increment('clicks'))
item.connect('activate', lambda *_: increment('menu_actions'))
menu_button.connect('button-press-event', lambda widget, event: menu.popup_at_pointer(event))
area.connect('button-press-event', lambda *_: increment('presses'))
area.connect('button-release-event', lambda *_: increment('releases'))
area.connect('motion-notify-event', lambda *_: increment('motions'))
window.connect('key-press-event', lambda widget, event: state['keys'].append({'key': Gdk.keyval_name(event.keyval), 'state': int(event.state)}))
def save():
    state['text'] = entry.get_text()
    state['menu_visible'] = menu.get_visible()
    state['bounds'] = {}
    for name, widget in [('entry', entry), ('button', button), ('menu_button', menu_button), ('area', area)]:
        x, y = widget.translate_coordinates(window, 0, 0)
        _, wx, wy = window.get_window().get_origin()
        allocation = widget.get_allocation()
        state['bounds'][name] = [wx+x+allocation.width//2, wy+y+allocation.height//2]
    if menu.get_visible():
        _, mx, my = menu.get_window().get_origin()
        allocation = item.get_allocation()
        state['bounds']['menu_item'] = [mx+allocation.x+allocation.width//2, my+allocation.y+allocation.height//2]
    temporary = out.with_suffix('.tmp')
    temporary.write_text(json.dumps(state))
    temporary.replace(out)
    return True
window.show_all()
entry.grab_focus()
GLib.timeout_add(10, save)
window.connect('destroy', Gtk.main_quit)
Gtk.main()
