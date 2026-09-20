"""Synthetic GTK data controls; app itself persists selection/edit/model oracle."""
import json
from pathlib import Path
import sys
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk, GLib
editing_widget=None
multi=len(sys.argv)>2 and sys.argv[2]=='range'
out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
state={'selected_id':None,'descending':False,'filtered':False,'edited':{},'lazy_loaded':False,'expanded':False}
w=Gtk.Window(title='Luda Data Qualification');w.set_default_size(1100 if multi else 1000,900 if multi else 720)
box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6);w.add(box)
bar=Gtk.Box(spacing=5);box.pack_start(bar,False,False,0)
store=Gtk.ListStore(int,str,str)
for i in range(120 if multi else 1200):store.append([i,f'Record {i:04}',f'Value {i:04}'])
filtered=store.filter_new();filtered.set_visible_func(lambda model,it,_:not state['filtered'] or model[it][0]>=10)
sorted_model=Gtk.TreeModelSort(model=filtered)
view=Gtk.TreeView(model=sorted_model);view.get_accessible().set_name('Records table')
view.set_headers_visible(True)
if multi:view.get_selection().set_mode(Gtk.SelectionMode.MULTIPLE)
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
 if multi:
  model,paths=selection.get_selected_rows();state['selected_ids']=[model[p][0] for p in paths];state['selection_events']=state.get('selection_events',0)+1
  action=state.pop('selection_fault',None)
  if action=='sort':sort(None)
  elif action=='replace':store[2][0]=4002;store[2][1]='Replaced record 4002'
 else:
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
if not multi:box.pack_start(tree,False,False,0)
if multi:
 controls=Gtk.Box(spacing=4);box.pack_start(controls,False,False,0)
 options=Gtk.ListBox();options.set_selection_mode(Gtk.SelectionMode.MULTIPLE);options.get_accessible().set_name('Range options')
 option_rows=[]
 for i in range(20):
  row=Gtk.ListBoxRow();row.add(Gtk.Label(label=f'Option {i:02}'));row.get_accessible().set_name(f'Option {i:02}');options.add(row);option_rows.append(row)
 option_scroll=Gtk.ScrolledWindow();option_scroll.set_size_request(-1,180);option_scroll.add(options);box.pack_start(option_scroll,False,False,0)
 def options_changed(*unused):state['option_ids']=[option_rows.index(row) for row in options.get_selected_rows()]
 options.connect('selected-rows-changed',options_changed)
 def fault(kind):state['selection_fault']=kind
 def duplicate(*unused):store[2][1]=store[1][1]
 def disable(*unused):option_rows[2].set_sensitive(False)
 def focus_other(*unused):
  other=Gtk.Window(title='Range focus observer');other.add(Gtk.Label(label='Owned focus fixture'));other.show_all();other.present();state['focus_window']=True
 for label,fn in [('Sort during selection',lambda *_:fault('sort')),('Replace during selection',lambda *_:fault('replace')),('Duplicate row label',duplicate),('Disable option two',disable),('Open focus observer',focus_other),('Single selection mode',lambda *_:view.get_selection().set_mode(Gtk.SelectionMode.SINGLE))]:
  button=Gtk.Button(label=label);button.connect('clicked',fn);controls.pack_start(button,False,False,0)

def persist():
 state['editing_widget_visible']=bool(editing_widget and editing_widget.get_mapped())
 state['editing_widget_focused']=bool(editing_widget and editing_widget.is_focus())
 state['expanded']=bool(tree.row_expanded(Gtk.TreePath.new_from_indices([0])))
 visible=view.get_visible_range();state['visible_range']=[p.to_string() for p in visible] if visible else None
 state['row_count']=len(sorted_model);state['first_id']=sorted_model[0][0] if len(sorted_model) else None
 p=out/'state.tmp';p.write_text(json.dumps(state));p.replace(out/'state.json');return True
GLib.timeout_add(50,persist);w.connect('destroy',Gtk.main_quit);w.show_all();Gtk.main()
