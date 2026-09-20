"""Bounded metadata fidelity/performance against owned GTK windows."""
import json
from pathlib import Path
import re
import subprocess
import tempfile
import time
from luda.common import run
from luda.x11 import X11

fixture='''import gi,json,os,sys\ngi.require_version("Gtk","3.0")\ngi.require_version("GdkX11","3.0")\nfrom gi.repository import Gtk,GdkX11,GLib\nfrom pathlib import Path\nwindows=[]\nfor i in range(10):\n w=Gtk.Window(title="Luda metadata "+str(i));w.set_wmclass("instance-"+str(i),"LudaMetadata");w.set_default_size(180,110);w.move(30+(i%5)*200,50+(i//5)*180);w.show_all();windows.append(w)\ndef ready():Path(sys.argv[1]).write_text(json.dumps([w.get_window().get_xid() for w in windows]));return False\nGLib.timeout_add(250,ready);Gtk.main()'''
with tempfile.TemporaryDirectory() as directory:
    output=Path(directory)/'ids.json';process=subprocess.Popen(['/usr/bin/python3','-c',fixture,str(output)])
    try:
        deadline=time.monotonic()+5
        while not output.exists() and time.monotonic()<deadline:time.sleep(.05)
        ids=json.loads(output.read_text());x=X11()
        metadata=x.window_metadata(ids)
        assert metadata['requested_count']==metadata['returned_count']==10 and not metadata['unavailable'],metadata
        for i,xid in enumerate(ids):
            item=metadata['windows'][xid]
            assert item['pid']==process.pid and item['wm_class']==['instance-'+str(i),'LudaMetadata'],item
            assert not item['unavailable_properties'],item
            raw=run(['xwininfo','-id',str(xid)]).decode()
            expected={key:int(re.search(pattern,raw).group(1)) for key,pattern in {'x':r'Absolute upper-left X:\s*(-?\d+)','y':r'Absolute upper-left Y:\s*(-?\d+)','width':r'Width:\s*(\d+)','height':r'Height:\s*(\d+)'}.items()}
            assert item['bounds']==expected,(item,expected)
            prop=run(['xprop','-id',str(xid),'_NET_FRAME_EXTENTS']).decode()
            extents=[int(v) for v in re.findall(r'\d+',prop.split('=',1)[1])]
            assert list(item['frame_extents'].values())==extents,(item,prop)
        old_times=[];batch_times=[]
        for _ in range(3):
            began=time.monotonic();x.geometries(ids);x.window_tokens(ids)
            for xid in ids:run(['xprop','-id',str(xid),'_NET_FRAME_EXTENTS','WM_CLASS'])
            old_times.append(time.monotonic()-began)
            began=time.monotonic();again=x.window_metadata(ids);batch_times.append(time.monotonic()-began)
            assert again['windows']==metadata['windows']
        # Only mutate metadata on fixture windows. Invalid optional properties
        # stay visible as diagnostics; invalid resource identity excludes a row.
        run(['xprop','-id',str(ids[0]),'-f','WM_CLASS','8s','-set','WM_CLASS','malformed'])
        run(['xprop','-id',str(ids[1]),'-f','_NET_FRAME_EXTENTS','32c','-set','_NET_FRAME_EXTENTS','1,2'])
        run(['xprop','-id',str(ids[2]),'-remove','_NET_WM_PID'])
        run(['xprop','-id',str(ids[3]),'-f','_LUDA_WINDOW_TOKEN','8s','-set','_LUDA_WINDOW_TOKEN','bad'])
        partial=x.window_metadata(ids+[0xffffffff])
        assert partial['requested_count']==11 and partial['returned_count']==9 and partial['unavailable_count']==2,partial
        assert {'xid':ids[3],'code':'INVALID_WINDOW_TOKEN'} in partial['unavailable']
        assert {'xid':0xffffffff,'code':'STALE_TARGET'} in partial['unavailable']
        assert {'property':'WM_CLASS','code':'INVALID_PROPERTY'} in partial['windows'][ids[0]]['unavailable_properties']
        assert {'property':'_NET_FRAME_EXTENTS','code':'INVALID_PROPERTY'} in partial['windows'][ids[1]]['unavailable_properties']
        assert partial['windows'][ids[2]]['pid'] is None
        print(json.dumps({'windows':10,'geometry_frame_class_pid':'independently verified','old_mean_ms':round(sum(old_times)/3*1000,2),'batch_mean_ms':round(sum(batch_times)/3*1000,2),'optional_and_missing_resources':'explicit diagnostics','batch_subprocesses':1,'prior_subprocesses':12}))
    finally:
        process.terminate();process.wait(timeout=5)
