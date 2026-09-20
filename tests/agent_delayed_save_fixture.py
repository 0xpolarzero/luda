"""Ordinary GTK save callback with a bounded simulated storage stall."""
import json,sys,time
from pathlib import Path
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,GLib
out=Path(sys.argv[1]);counter=0
window=Gtk.Window(title='Field Notes');window.set_default_size(640,420)
box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12);box.set_border_width(20);window.add(box)
box.pack_start(Gtk.Label(label='Site visit report'),False,False,0)
text=Gtk.TextView();text.get_accessible().set_name('Report');box.pack_start(text,True,True,0)
status=Gtk.Label(label='Not saved');status.get_accessible().set_name('Save status');box.pack_start(status,False,False,0)
button=Gtk.Button(label='Save report');box.pack_start(button,False,False,0)
def persist(name,value):
 temporary=out/(name+'.tmp');temporary.write_text(json.dumps(value,ensure_ascii=False));temporary.replace(out/(name+'.json'))
def save(*unused):
 global counter
 counter+=1
 buffer=text.get_buffer();start,end=buffer.get_bounds();value=buffer.get_text(start,end,True)
 accepted={'submissions':counter,'text':value,'accepted_monotonic':time.monotonic()};persist('accepted',accepted)
 status.set_text('Saving report…')
 def finish():
  started=time.monotonic();time.sleep(20)
  persist('saved',{**accepted,'stall_started':started,'committed_monotonic':time.monotonic()})
  status.set_text('Report saved — receipt '+str(counter));return False
 # Give the ordinary UI one paint before its synchronous storage callback stalls.
 GLib.timeout_add(100,finish)
button.connect('clicked',save);window.connect('destroy',Gtk.main_quit);window.show_all();Gtk.main()
