"""Read real D-Bus hints on a private bus; never lock the user's desktop."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from luda.session_state import session_state

if len(sys.argv)==1:
    env=dict(os.environ);env.pop('XDG_SESSION_ID',None)
    subprocess.run(['dbus-run-session','--',sys.executable,__file__,'private'],env=env,check=True,timeout=15)
else:
    assert session_state()['state']=='unknown'
    with tempfile.TemporaryDirectory() as directory:
        base=Path(directory);flag=base/'active';flag.write_text('true');ready=base/'ready';calls=base/'calls'
        source='''import gi,sys
from pathlib import Path
gi.require_version('Gio','2.0')
from gi.repository import Gio,GLib
flag,ready,calls=map(Path,sys.argv[1:])
bus=Gio.bus_get_sync(Gio.BusType.SESSION,None)
node=Gio.DBusNodeInfo.new_for_xml('<node><interface name="org.xfce.ScreenSaver"><method name="GetActive"><arg type="b" direction="out"/></method></interface></node>')
def method(bus,sender,path,interface,name,parameters,invocation):
 with calls.open('a') as f:f.write(name+'\\n')
 invocation.return_value(GLib.Variant('(b)',(flag.read_text()=='true',)))
bus.register_object('/org/xfce/ScreenSaver',node.interfaces[0],method,None,None)
def acquired(*args):ready.write_text('ready')
owner=Gio.bus_own_name_on_connection(bus,'org.xfce.ScreenSaver',Gio.BusNameOwnerFlags.NONE,acquired,None)
GLib.MainLoop().run()
'''
        child=subprocess.Popen(['/usr/bin/python3','-c',source,str(flag),str(ready),str(calls)])
        try:
            deadline=time.monotonic()+4
            while not ready.exists():
                assert time.monotonic()<deadline,'private provider not ready';time.sleep(.02)
            result=session_state();assert result['state']=='screensaver_active' and result['input_ready'] is False,result
            flag.write_text('false')
            result=session_state();assert result['state']=='inactive' and result['input_ready'] is None,result
            assert calls.read_text().splitlines()==['GetActive','GetActive']
            print(json.dumps({'unavailable':'unknown','active':'screensaver_active','inactive':'not proof of unlocked','provider_methods':['GetActive','GetActive']}))
        finally:
            child.terminate();child.wait(timeout=3)
