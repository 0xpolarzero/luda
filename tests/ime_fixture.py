"""Independent GTK3 oracle for real built-in Unicode input-method preedit."""
import json
from pathlib import Path
import sys
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk
output=Path(sys.argv[1]);kind=sys.argv[2]
window=Gtk.Window(title='Luda IME fixture');window.set_default_size(500,240)
widget=Gtk.Entry() if kind=='entry' else Gtk.TextView()
widget.get_accessible().set_name('Composition field');window.add(widget)
state={'preedit':'','preedit_events':[],'committed':''}
def save():
    state['committed']=widget.get_text() if kind=='entry' else widget.get_buffer().get_text(*widget.get_buffer().get_bounds(),True)
    temp=output.with_suffix('.tmp');temp.write_text(json.dumps(state,ensure_ascii=False));temp.replace(output)
def preedit(widget,text):
    state['preedit']=text;state['preedit_events'].append(text);save()
widget.connect('preedit-changed',preedit)
if kind=='entry':widget.connect('changed',lambda *_:save());widget.set_text('BASE')
else:widget.get_buffer().connect('changed',lambda *_:save());widget.get_buffer().set_text('BASE')
window.connect('destroy',Gtk.main_quit);window.show_all();widget.grab_focus();save();Gtk.main()
