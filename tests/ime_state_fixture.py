"""App-owned early/late signal oracles; no external application injection."""
import gi,json,sys
from pathlib import Path
gi.require_version('Gtk',sys.argv[2])
from gi.repository import Gtk,GLib,GObject
out=Path(sys.argv[1]);kind=sys.argv[3];version=sys.argv[2];state={'early_events':0,'late_events':0,'late_attached':False,'preedit_nonempty':False,'preedit_characters':0,'late_known':False}
app=Gtk.Application(application_id='org.luda.imereadonly') if version=='4.0' else None
widget=None

def save():
 if widget is None:return
 state['committed']=widget.get_text() if kind=='entry' else widget.get_buffer().get_text(*widget.get_buffer().get_bounds(),True)
 p=out.with_suffix('.tmp');p.write_text(json.dumps(state));p.replace(out)
def activate(*unused):
 global widget
 window=Gtk.ApplicationWindow(application=app,title='Luda IME state audit') if app else Gtk.Window(title='Luda IME state audit')
 window.set_default_size(600,300);widget=Gtk.Entry() if kind=='entry' else Gtk.TextView()
 if version=='4.0':window.set_child(widget);widget.update_property([Gtk.AccessibleProperty.LABEL],['Composition field'])
 else:window.add(widget);widget.get_accessible().set_name('Composition field');widget.get_accessible().set_accessible_id('luda-ime-observed-field')
 signal_widget=widget.get_delegate() if version=='4.0' and kind=='entry' else widget
 if version=='4.0' and kind=='entry':signal_widget.update_property([Gtk.AccessibleProperty.LABEL],['Composition field'])
 state['widget_type']=type(widget).__name__;state['signal_widget_type']=type(signal_widget).__name__
 state['public_preedit_methods']=[n for n in dir(signal_widget) if 'preedit' in n or 'im_context' in n]
 state['gtk_version']=[Gtk.get_major_version(),Gtk.get_minor_version(),Gtk.get_micro_version()]
 state['input_context_properties']=[p.name for p in signal_widget.list_properties() if 'context' in p.name or 'preedit' in p.name or 'im-module' in p.name]
 def late(w,text):state.update(late_events=state['late_events']+1,late_known=True,late_nonempty=bool(text));save()
 def attach_late(expected_events):
  if state['early_events']!=expected_events:return False
  if state['late_attached']:return False
  signal_widget.connect('preedit-changed',late);state['late_attached']=True;save();return False
 def early(w,text):
  state.update(early_events=state['early_events']+1,preedit_nonempty=bool(text),preedit_characters=len(text));save()
  if text and not state['late_attached']:GLib.timeout_add(250,attach_late,state['early_events'])
 signal_widget.connect('preedit-changed',early)
 if kind=='entry':widget.set_text('BASE');widget.connect('changed',lambda *_:save())
 else:widget.get_buffer().set_text('BASE');widget.get_buffer().connect('changed',lambda *_:save())
 if app:window.present()
 else:window.connect('destroy',Gtk.main_quit);window.show_all()
 widget.grab_focus();save()
if app:app.connect('activate',activate);app.run([])
else:activate();Gtk.main()
