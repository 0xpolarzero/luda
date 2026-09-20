"""Fixed GTK row slots with delayed page loads and separate stable record IDs."""
import gi,json,sys
from pathlib import Path
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,Gdk,GLib
out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
state={'page':0,'generation':0,'loading':False,'blocked':False,'filtered':False,'loaded_pages':[],'scroll_requests':0,'selected_id':None,'selection_events':0,'end':False}
w=Gtk.Window(title='Recycled Records');w.set_default_size(850,550);box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10);w.add(box)
bar=Gtk.Box(spacing=8);box.pack_start(bar,False,False,0)
status=Gtk.Label();box.pack_start(status,False,False,0)
store=Gtk.ListStore(str,str,int)
for i in range(4):store.append(['','',0])
view=Gtk.TreeView(model=store);view.get_accessible().set_name('Recycled records')
for column,title in [(0,'Label'),(1,'Record identity')]:
 renderer=Gtk.CellRendererText();renderer.set_property('ypad',12);view.append_column(Gtk.TreeViewColumn(title,renderer,text=column))
scroll=Gtk.ScrolledWindow();scroll.add(view);box.pack_start(scroll,True,True,0)
def publish():
 tmp=out/'state.tmp';tmp.write_text(json.dumps(state));tmp.replace(out/'state.json');return True
def load(page):
 state['page']=page;state['loading']=False;state['generation']+=1;state['end']=page==2;state['selected_id']=None
 view.get_selection().unselect_all()
 base=100 if state['filtered'] else 0
 for slot,row in enumerate(store):
  identifier=base+page*4+slot;row[0]='Duplicate' if page>0 and slot<2 else 'Label '+str(identifier);row[1]=f'Record {identifier:03}';row[2]=identifier
 state['visible_ids']=[row[2] for row in store];state['loaded_pages'].append({'page':page,'filtered':state['filtered'],'ids':state['visible_ids']});view.set_sensitive(True)
 status.set_text('End of data' if state['end'] else f'Page {page+1} ready');publish();return False
def scrolling(_widget,event):
 if event.direction not in (Gdk.ScrollDirection.DOWN,Gdk.ScrollDirection.UP):return True
 state['scroll_requests']+=1
 if state['loading'] or state['blocked'] or (state['end'] and event.direction==Gdk.ScrollDirection.DOWN):publish();return True
 page=max(0,min(2,state['page']+(1 if event.direction==Gdk.ScrollDirection.DOWN else -1)))
 if page==state['page']:return True
 state['loading']=True;view.set_sensitive(False);status.set_text('Loading records');publish();GLib.timeout_add(450,load,page);return True
view.add_events(Gdk.EventMask.SCROLL_MASK);view.connect('scroll-event',scrolling)
def selected(selection):
 model,it=selection.get_selected();state['selected_id']=model[it][2] if it else None;state['selection_events']+=1;publish()
view.get_selection().connect('changed',selected)
def control(_button,kind):
 if kind=='Reset':state['blocked']=False;state['filtered']=False;load(0)
 elif kind=='Filter':state['filtered']=not state['filtered'];load(0)
 else:state['blocked']=not state['blocked'];status.set_text('Loading stalled' if state['blocked'] else 'Loading resumed');publish()
for name in ('Reset','Filter','Stall loading'):
 b=Gtk.Button(label=name);b.connect('clicked',control,name);bar.pack_start(b,False,False,0)
load(0);w.connect('destroy',Gtk.main_quit);w.show_all();GLib.timeout_add(100,publish);Gtk.main()
