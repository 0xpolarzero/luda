"""Owned GTK overlays with independent action/focus outcome counters."""
import json
import sys
from pathlib import Path
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,Gdk,GLib
out=Path(sys.argv[1]);state={'proof':0,'tooltip_presses':0,'saved':0,'cancelled':0,'default':'none'}
w=Gtk.Window(title='Luda overlay oracle');w.set_default_size(500,350);w.move(120,100)
box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8);w.add(box)
def button(label,callback):
 b=Gtk.Button(label=label);box.pack_start(b,True,True,0);b.connect('clicked',callback);return b
def count(key):state[key]+=1
proof=button('Proof action',lambda *_:count('proof'))
popup=Gtk.Window(type=Gtk.WindowType.POPUP);popup.set_transient_for(w);popup.set_type_hint(Gdk.WindowTypeHint.TOOLTIP)
popup.add(Gtk.Label(label='Read-only help over Proof action'));popup.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
popup.connect('button-press-event',lambda *_:count('tooltip_presses'))
def show_popup(*_):
 x,y=w.get_position();a=proof.get_allocation();popup.set_size_request(a.width,a.height);popup.move(x+a.x,y+a.y);popup.show_all()
button('Show overlapping help',show_popup)
notice=Gtk.Window(title='Luda attention notification');notice.set_transient_for(w);notice.set_type_hint(Gdk.WindowTypeHint.NOTIFICATION)
close=Gtk.Button(label='Dismiss attention');notice.add(close);close.connect('clicked',lambda *_:(notice.hide(),w.present()))
button('Show attention window',lambda *_:(notice.show_all(),notice.present()))
def dialog(*_):
 d=Gtk.Dialog(title='Luda changing default',transient_for=w,modal=True);d.add_button('Cancel operation',Gtk.ResponseType.CANCEL);d.add_button('Save operation',Gtk.ResponseType.OK)
 d.set_default_response(Gtk.ResponseType.OK);state['default']='save'
 def changed():d.set_default_response(Gtk.ResponseType.CANCEL);state['default']='cancel';return False
 def response(widget,value):count('saved' if value==Gtk.ResponseType.OK else 'cancelled');d.destroy()
 d.connect('response',response);d.show_all();GLib.timeout_add(350,changed)
button('Show changing default',dialog)
def escape(widget,event):
 if event.keyval==Gdk.KEY_Escape:popup.hide();return True
 return False
w.connect('key-press-event',escape)
def save():
 temp=out.with_suffix('.tmp');temp.write_text(json.dumps(state));temp.replace(out);return True
GLib.timeout_add(20,save);w.connect('destroy',Gtk.main_quit);w.show_all();Gtk.main()
