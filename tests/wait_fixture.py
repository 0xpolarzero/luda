"""Owned delayed-widget and continuous-animation fixture with independent state file."""
import json
from pathlib import Path
import sys
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk, GLib

folder=Path(sys.argv[1]);folder.mkdir(parents=True,exist_ok=True)
window=Gtk.Window(title='Luda Wait Qualification');window.set_default_size(500,300)
box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=20);window.add(box)
label=Gtk.Label(label='Frame 0');box.pack_start(label,False,False,20)
state={'frame':0,'animating':True,'target_present':False,'command_id':None}
target=None

def publish():
    temporary=folder/'state.tmp'
    temporary.write_text(json.dumps(state))
    temporary.replace(folder/'state.json')

def add():
    global target
    target=Gtk.Button(label='Delayed control')
    box.pack_start(target,False,False,10);target.show()
    state['target_present']=True;publish()
    return False

def remove():
    global target
    if target:target.destroy();target=None
    state['target_present']=False;publish()
    return False

def tick():
    try:
        command=json.loads((folder/'command.json').read_text())
    except (OSError,ValueError):
        command={}
    if command.get('id') is not None and command.get('id')!=state['command_id']:
        state['command_id']=command['id']
        if command['action']=='cycle':
            GLib.timeout_add(300,add);GLib.timeout_add(1000,remove)
        elif command['action']=='stop':
            state['animating']=False
    if state['animating']:
        state['frame']+=1;label.set_text('Frame '+str(state['frame']))
    publish();return True

window.connect('destroy',Gtk.main_quit);window.show_all();GLib.timeout_add(35,tick);publish();Gtk.main()
