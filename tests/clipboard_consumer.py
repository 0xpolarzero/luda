"""Independent delayed GTK clipboard consumer; no editable widget owns PRIMARY."""
import json
from pathlib import Path
import sys
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GLib

output = Path(sys.argv[1])
delay = int(sys.argv[2])
state = {'requests': 0, 'received': []}
def save():
    temporary = output.with_suffix('.tmp')
    temporary.write_text(json.dumps(state, ensure_ascii=False))
    temporary.replace(output)
def consume():
    value = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).wait_for_text()
    state['received'].append(value)
    save()
    return False
def key(window, event):
    if event.keyval in (Gdk.KEY_v, Gdk.KEY_V) and event.state & Gdk.ModifierType.CONTROL_MASK:
        state['requests'] += 1
        save()
        GLib.timeout_add(delay, consume)
        return True
    return False
window = Gtk.Window(title='Luda owned delayed clipboard consumer')
window.set_default_size(400, 180)
window.add(Gtk.Label(label='Passive clipboard reader: no commands are executed.'))
window.connect('key-press-event', key)
window.connect('destroy', Gtk.main_quit)
window.show_all()
save()
Gtk.main()
