"""Synthetic read-only screen state provider on the caller-owned private bus."""
import gi,sys
from pathlib import Path
gi.require_version('Gio','2.0')
from gi.repository import Gio,GLib
flag,ready,calls=map(Path,sys.argv[1:])
bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
node=Gio.DBusNodeInfo.new_for_xml('<node><interface name="org.xfce.ScreenSaver"><method name="GetActive"><arg type="b" direction="out"/></method></interface></node>')
def method(bus,sender,path,interface,name,parameters,invocation):
 with calls.open('a') as f:f.write(name+'\n')
 invocation.return_value(GLib.Variant('(b)',(flag.read_text()=='true',)))
bus.register_object('/org/xfce/ScreenSaver',node.interfaces[0],method,None,None)
def acquired(*args):ready.write_text('ready')
owner=Gio.bus_own_name_on_connection(bus,'org.xfce.ScreenSaver',Gio.BusNameOwnerFlags.NONE,acquired,None)
GLib.MainLoop().run()
