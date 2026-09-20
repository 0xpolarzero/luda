"""Native GTK multi-selection task; record IDs and event history are app-owned."""
import gi,json,sys
from pathlib import Path
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,GLib
out=Path(sys.argv[1]);events=[];state={}
w=Gtk.Window(title='Range Desk');w.set_default_size(700,650);box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12);w.add(box)
heading=Gtk.Label(label='Records');box.pack_start(heading,False,False,0)
store=Gtk.ListStore(int,str)
for number in range(1,9):store.append([number,f'Record {number:03}'])
view=Gtk.TreeView(model=store);view.get_accessible().set_name('Records table');renderer=Gtk.CellRendererText();renderer.set_property('ypad',14);view.append_column(Gtk.TreeViewColumn('Record',renderer,text=1));selection=view.get_selection();selection.set_mode(Gtk.SelectionMode.MULTIPLE)
box.pack_start(view,True,True,0);receipt=Gtk.Label();box.pack_start(receipt,False,False,0)
def save():
 model,paths=selection.get_selected_rows();ids=[model[p][0] for p in paths];state.update(selected_ids=ids,events=list(events),row_count=len(store));receipt.set_text('Selected: '+', '.join(f'Record {n:03}' for n in ids));tmp=out/'state.tmp';tmp.write_text(json.dumps(state));tmp.replace(out/'state.json');return True
def changed(_):
 model,paths=selection.get_selected_rows();events.append([model[p][0] for p in paths]);save()
selection.select_path(Gtk.TreePath.new_from_indices([5]));selection.connect('changed',changed);save();w.connect('destroy',Gtk.main_quit);w.show_all();GLib.timeout_add(100,save);Gtk.main()
