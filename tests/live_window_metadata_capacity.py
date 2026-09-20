"""Qualify the full metadata batch bound on 512 disposable X resources."""
import ctypes as C
import json
import os
import select
import subprocess
import time
from unittest.mock import patch
from luda._x11_helper import _NativeX11
from luda.common import DesktopError
from luda.x11 import X11

reader,writer=os.pipe()
server=subprocess.Popen(['Xvfb','-displayfd',str(writer),'-screen','0','640x480x24','-nolisten','tcp'],pass_fds=(writer,),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
os.close(writer);native=None
try:
    assert select.select([reader],[],[],5)[0]
    number=os.read(reader,32).decode().strip();os.close(reader);assert number.isdigit()
    with patch.dict(os.environ,{'DISPLAY':':'+number}):
        native=_NativeX11();x=native.lib
        x.XCreateSimpleWindow.argtypes=[C.c_void_p,C.c_ulong,C.c_int,C.c_int,C.c_uint,C.c_uint,C.c_uint,C.c_ulong,C.c_ulong];x.XCreateSimpleWindow.restype=C.c_ulong
        x.XSync.argtypes=[C.c_void_p,C.c_int]
        ids=[x.XCreateSimpleWindow(native.display,native.root,0,0,10,10,0,0,0) for _ in range(512)]
        x.XSync(native.display,False)
        client=X11();start=time.monotonic();result=client.window_metadata(ids);elapsed=time.monotonic()-start
        assert result['requested_count']==result['unique_requested_count']==result['returned_count']==512,result
        assert result['unavailable_count']==0 and len(result['windows'])==512
        assert all(item['bounds']=={'x':0,'y':0,'width':10,'height':10} and len(item['generation'])==32 and len(item['unavailable_properties'])==3 for item in result['windows'].values())
        try:client.window_metadata(ids+[ids[0]]);raise AssertionError('oversized batch accepted')
        except DesktopError as exc:assert exc.code=='INVALID_ARGUMENT'
        print(json.dumps({'requested':512,'returned':512,'seconds':round(elapsed,3),'optional_properties':'explicitly missing','513_resources':'rejected before dispatch'}))
finally:
    if native is not None:native.close()
    server.terminate();server.wait(timeout=5)
