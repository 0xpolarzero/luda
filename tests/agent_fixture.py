"""Unseen-to-agent form; the harness independently reads committed values."""
import json
from pathlib import Path
import sys
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk

output=Path(sys.argv[1])
window=Gtk.Window(title='Luda agent task');window.set_default_size(560,440)
box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12);box.set_border_width(20);window.add(box)
box.pack_start(Gtk.Label(label='Delivery preferences'),False,False,0)
text=Gtk.TextView();text.get_accessible().set_name('Delivery note');box.pack_start(text,True,True,0)
updates=Gtk.CheckButton(label='Send updates');box.pack_start(updates,False,False,0)
standard=Gtk.RadioButton.new_with_label_from_widget(None,'Standard delivery')
express=Gtk.RadioButton.new_with_label_from_widget(standard,'Express delivery')
box.pack_start(standard,False,False,0);box.pack_start(express,False,False,0)
status=Gtk.Label(label='Not saved');status.get_accessible().set_name('Save status');box.pack_start(status,False,False,0)
button=Gtk.Button(label='Save preferences');box.pack_start(button,False,False,0)
def save(*unused):
    buffer=text.get_buffer();start,end=buffer.get_bounds()
    temporary=output.with_suffix('.tmp')
    temporary.write_text(json.dumps({'note':buffer.get_text(start,end,True),'updates':updates.get_active(),'express':express.get_active()},ensure_ascii=False))
    temporary.replace(output);status.set_text('Preferences saved')
button.connect('clicked',save)
window.connect('destroy',Gtk.main_quit);window.show_all();Gtk.main()
