"""GTK RTL entry with independent logical text and Pango cursor geometry oracle."""
import json
from pathlib import Path
import sys
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib, Pango
out = Path(sys.argv[1])
window = Gtk.Window(title='Luda RTL entry oracle')
window.set_default_size(900, 160)
window.set_direction(Gtk.TextDirection.RTL)
entry = Gtk.Entry()
entry.set_direction(Gtk.TextDirection.RTL)
entry.set_alignment(1)
entry.get_accessible().set_name('Mixed RTL text')
window.add(entry)
def publish():
    text = entry.get_text()
    position = entry.get_position()
    index = entry.text_index_to_layout_index(len(text[:position].encode('utf-8')))
    strong, weak = entry.get_layout().get_cursor_pos(index)
    xoff, yoff = entry.get_layout_offsets()
    state = {'text': text, 'position': position, 'selection': entry.get_selection_bounds(),
             'direction': entry.get_direction().value_nick,
             'strong_x': xoff + strong.x / Pango.SCALE,
             'weak_x': xoff + weak.x / Pango.SCALE, 'focused': entry.has_focus()}
    (out / 'state.tmp').write_text(json.dumps(state))
    (out / 'state.tmp').replace(out / 'state.json')
    return True
window.connect('destroy', Gtk.main_quit)
window.show_all()
entry.grab_focus()
GLib.timeout_add(20, publish)
Gtk.main()
