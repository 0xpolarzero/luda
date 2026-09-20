"""Offline native GUI with independent persisted state for integration assertions."""
import gi
import json
import sys
import os
import time
from pathlib import Path
gi.require_version('Gtk','3.0')
from gi.repository import Gtk, GLib

out=Path(sys.argv[1]);out.mkdir(exist_ok=True)
window=Gtk.Window(title='Luda Contract Fixture')
window.set_default_size(620,440)
box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8);window.add(box)
view=Gtk.TextView();view.set_name('contract-editor');view.get_accessible().set_name('Contract text')
scroll=Gtk.ScrolledWindow();scroll.add(view);box.pack_start(scroll,True,True,0)
button=Gtk.Button(label='Record action');box.pack_start(button,False,False,0)
entry=Gtk.Entry();entry.set_visibility(False);entry.get_accessible().set_name('Secret input');box.pack_start(entry,False,False,0)
disabled=Gtk.Button(label='Disabled action');disabled.set_sensitive(False);box.pack_start(disabled,False,False,0)
hidden=Gtk.Entry();hidden.get_accessible().set_name('Hidden text');hidden.set_no_show_all(True);box.pack_start(hidden,False,False,0)
state={'clicks':0,'text':'','pointer':None}
# Opt-in timing fault: defer the real GTK default paste handler, never set text.
paste_delay=int(os.environ.get('LUDA_TEST_PASTE_DELAY_MS','0'))
assert 0 <= paste_delay <= 2000
if paste_delay:
 def delayed_paste(widget):
  widget.stop_emission_by_name('paste-clipboard')
  state['paste_requests']=state.get('paste_requests',0)+1
  state['paste_requested_at']=time.monotonic()
  def deliver():
   state['paste_delivered_at']=time.monotonic()
   widget.handler_block(paste_handler)
   try:widget.emit('paste-clipboard')
   finally:widget.handler_unblock(paste_handler)
   return False
  GLib.timeout_add(paste_delay,deliver)
 paste_handler=view.connect('paste-clipboard',delayed_paste)
def clicked(*_):
 state['clicks']+=1
button.connect('clicked',clicked)
def save():
 b=view.get_buffer();state['text']=b.get_text(b.get_start_iter(),b.get_end_iter(),True)
 (out/'state.tmp').write_text(json.dumps(state,ensure_ascii=False))
 (out/'state.tmp').replace(out/'state.json')
 return True
GLib.timeout_add(30,save)
window.connect('destroy',Gtk.main_quit)
window.show_all();view.grab_focus();Gtk.main()
