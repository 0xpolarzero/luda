"""Offline GTK4 qualification app with independently persisted state."""
import json
import sys
from pathlib import Path
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,GLib
out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
app=Gtk.Application(application_id='org.luda.toolkitfixture')
modal=None;dialog_count=0

def activate(app):
 w=Gtk.ApplicationWindow(application=app,title='Luda GTK4 Fixture');w.set_default_size(620,480)
 box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8);w.set_child(box)
 editor=Gtk.TextView();editor.update_property([Gtk.AccessibleProperty.LABEL],['Toolkit text'])
 editor.set_vexpand(True);box.append(editor)
 check=Gtk.CheckButton(label='Toolkit check');box.append(check)
 value=Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL,0,100,1)
 value.update_property([Gtk.AccessibleProperty.LABEL],['Toolkit value']);box.append(value)
 secret=Gtk.PasswordEntry();secret.update_property([Gtk.AccessibleProperty.LABEL],['Toolkit secret']);box.append(secret)
 disabled=Gtk.Button(label='Toolkit disabled');disabled.set_sensitive(False);box.append(disabled)
 button=Gtk.Button(label='Open toolkit dialog');box.append(button)
 def show_modal(*_):
  global modal,dialog_count
  modal=Gtk.Window(title='Luda GTK4 Modal',transient_for=w,modal=True)
  modal.set_default_size(300,150)
  close=Gtk.Button(label='Close toolkit dialog');close.connect('clicked',lambda *_:modal.close())
  modal.set_child(close);dialog_count+=1;modal.present()
 button.connect('clicked',show_modal)
 def save():
  b=editor.get_buffer()
  state={'text':b.get_text(b.get_start_iter(),b.get_end_iter(),True),'checked':check.get_active(),
         'value':value.get_value(),'caret':b.get_iter_at_mark(b.get_insert()).get_offset(),
         'selection':[it.get_offset() for it in b.get_selection_bounds()],
         'focused':editor.has_focus(),'dialog_visible':bool(modal and modal.get_visible()),'dialog_count':dialog_count}
  (out/'state.tmp').write_text(json.dumps(state,ensure_ascii=False));(out/'state.tmp').replace(out/'state.json');return True
 GLib.timeout_add(30,save);w.present();editor.grab_focus()
app.connect('activate',activate);app.run([])
