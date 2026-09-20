"""Synthetic GTK data controls; app itself persists selection/edit/model oracle."""
import json
from pathlib import Path
import sys
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk, GLib
editing_widget=None
out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
state={'selected_id':None,'descending':False,'filtered':False,'edited':{},'lazy_loaded':False,'expanded':False}
w=Gtk.Window(title='Luda Data Qualification');w.set_default_size(1000,720)
box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6);w.add(box)
bar=Gtk.Box(spacing=5);box.pack_start(bar,False,False,0)
store=Gtk.ListStore(int,str,str)
for i in range(1200):store.append([i,f'Record {i:04}',f'Value {i:04}'])
filtered=store.filter_new();filtered.set_visible_func(lambda model,it,_:not state['filtered'] or model[it][0]>=10)
sorted_model=Gtk.TreeModelSort(model=filtered)
view=Gtk.TreeView(model=sorted_model);view.get_accessible().set_name('Records table')
view.set_headers_visible(True)
for col,title in [(1,'Identity'),(2,'Editable value')]:
 renderer=Gtk.CellRendererText();renderer.set_property('editable',col==2)
 if col==2:
  def edited(renderer,path,text):
   it=sorted_model.get_iter(path);identifier=sorted_model[it][0]
   for row in store:
    if row[0]==identifier:row[2]=text;break
   state['edited'][str(identifier)]=text
  renderer.connect('edited',edited)
  def editing_started(renderer,widget,path):
   global editing_widget
   editing_widget=widget;state['editing_path']=path
  renderer.connect('editing-started',editing_started)
 view.append_column(Gtk.TreeViewColumn(title,renderer,text=col))
scrolled=Gtk.ScrolledWindow();scrolled.set_policy(Gtk.PolicyType.AUTOMATIC,Gtk.PolicyType.AUTOMATIC);scrolled.add(view);box.pack_start(scrolled,True,True,0)
def selected(selection):
 model,it=selection.get_selected();state['selected_id']=model[it][0] if it else None
view.get_selection().connect('changed',selected)
def sort(_):
 state['descending']=not state['descending'];sorted_model.set_sort_column_id(0,Gtk.SortType.DESCENDING if state['descending'] else Gtk.SortType.ASCENDING)
def filter_rows(_):state['filtered']=not state['filtered'];filtered.refilter()
def reset(_):
 state['descending']=False;state['filtered']=False;filtered.refilter();sorted_model.set_sort_column_id(0,Gtk.SortType.ASCENDING);view.scroll_to_cell(Gtk.TreePath.new_from_indices([0]))
for title,fn in [('Reverse sort',sort),('Filter first ten',filter_rows),('Reset data',reset)]:
 b=Gtk.Button(label=title);b.connect('clicked',fn);bar.pack_start(b,False,False,0)
identity_button=Gtk.Button(label='Identity action');identity_button.get_accessible().set_name('x'*300+' first')
identity_button.connect('clicked',lambda *_:state.update(identity_clicks=state.get('identity_clicks',0)+1));bar.pack_start(identity_button,False,False,0)
rename=Gtk.Button(label='Rename long identity')
def rename_identity(_):identity_button.get_accessible().set_name('x'*300+' second');state['identity_renamed']=True
rename.connect('clicked',rename_identity);bar.pack_start(rename,False,False,0)
tree_store=Gtk.TreeStore(str);root=tree_store.append(None,['Lazy group']);tree_store.append(root,['Loading placeholder'])
tree=Gtk.TreeView(model=tree_store);tree.get_accessible().set_name('Lazy tree');tree.append_column(Gtk.TreeViewColumn('Tree',Gtk.CellRendererText(),text=0));tree.set_size_request(-1,180)
def expanded(tree,it,path):
 state['expanded']=True
 if not state['lazy_loaded']:
  state['lazy_loaded']=True;placeholder=tree_store.iter_children(it)
  for i in range(4):tree_store.append(it,[f'Lazy child {i}'])
  tree_store.remove(placeholder)
tree.connect('row-expanded',expanded);tree.connect('row-collapsed',lambda *_:state.update(expanded=False))
box.pack_start(tree,False,False,0)
def persist():
 state['editing_widget_visible']=bool(editing_widget and editing_widget.get_mapped())
 state['editing_widget_focused']=bool(editing_widget and editing_widget.is_focus())
 state['expanded']=bool(tree.row_expanded(Gtk.TreePath.new_from_indices([0])))
 visible=view.get_visible_range();state['visible_range']=[p.to_string() for p in visible] if visible else None
 state['row_count']=len(sorted_model);state['first_id']=sorted_model[0][0] if len(sorted_model) else None
 p=out/'state.tmp';p.write_text(json.dumps(state));p.replace(out/'state.json');return True
GLib.timeout_add(50,persist);w.connect('destroy',Gtk.main_quit);w.show_all();Gtk.main()
