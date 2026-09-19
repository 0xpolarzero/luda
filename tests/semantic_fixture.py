"""Offline native GUI with independent persisted state for integration assertions."""
import gi
import json
import sys
from pathlib import Path
gi.require_version('Gtk','3.0')
from gi.repository import Gtk, GLib

out=Path(sys.argv[1]);out.mkdir(exist_ok=True)
window=Gtk.Window(title='Luda Semantic Fixture')
window.set_default_size(620,440)
box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8);window.add(box)
view=Gtk.TextView();view.set_name('contract-editor');view.get_accessible().set_name('Contract text')
scroll=Gtk.ScrolledWindow();scroll.add(view);box.pack_start(scroll,True,True,0)
button=Gtk.Button(label='Record action');box.pack_start(button,False,False,0)
entry=Gtk.Entry();entry.set_visibility(False);entry.get_accessible().set_name('Secret input');box.pack_start(entry,False,False,0)
disabled=Gtk.Button(label='Disabled action');disabled.set_sensitive(False);box.pack_start(disabled,False,False,0)
hidden=Gtk.Entry();hidden.get_accessible().set_name('Hidden text');hidden.set_no_show_all(True);box.pack_start(hidden,False,False,0)
check=Gtk.CheckButton(label='Semantic check');box.pack_start(check,False,False,0)
scale=Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,0,100,1);scale.get_accessible().set_name('Semantic value');box.pack_start(scale,False,False,0)
expander=Gtk.Expander(label='Semantic expander');expander.add(Gtk.Label(label='Expanded contents'));box.pack_start(expander,False,False,0)
state={'clicks':0,'text':'','pointer':None}
def clicked(*_):
 state['clicks']+=1
button.connect('clicked',clicked)
def save():
 b=view.get_buffer();state['text']=b.get_text(b.get_start_iter(),b.get_end_iter(),True)
 state['checked']=check.get_active();state['value']=scale.get_value();state['expanded']=expander.get_expanded()
 state['caret']=b.get_iter_at_mark(b.get_insert()).get_offset()
 state['selection']=[it.get_offset() for it in b.get_selection_bounds()]
 (out/'state.tmp').write_text(json.dumps(state,ensure_ascii=False))
 (out/'state.tmp').replace(out/'state.json')
 return True
GLib.timeout_add(30,save)
window.connect('destroy',Gtk.main_quit)
window.show_all();view.grab_focus();Gtk.main()
