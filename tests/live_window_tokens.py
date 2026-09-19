"""Real same-XID destruction/recreation, concurrent readers, and grab cleanup."""
import concurrent.futures
import ctypes as C
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
from unittest.mock import patch
from luda.common import DesktopError,run
from luda.x11 import X11

class Cookie(C.Structure):_fields_=[('sequence',C.c_uint)]

readfd,writefd=os.pipe()
p=subprocess.Popen(['Xvfb','-displayfd',str(writefd),'-screen','0','640x480x24','-nolisten','tcp'],pass_fds=(writefd,),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
os.close(writefd);connection=None
try:
    assert select.select([readfd],[],[],5)[0]
    number=os.read(readfd,32).decode().strip();os.close(readfd)
    assert number.isdigit()
    with patch.dict(os.environ,{'DISPLAY':':'+number}):
        first=X11();second=X11();root=first.root
        x=C.CDLL('libxcb.so.1')
        x.xcb_connect.argtypes=[C.c_char_p,C.POINTER(C.c_int)];x.xcb_connect.restype=C.c_void_p
        x.xcb_disconnect.argtypes=[C.c_void_p]
        x.xcb_generate_id.argtypes=[C.c_void_p];x.xcb_generate_id.restype=C.c_uint32
        x.xcb_create_window_checked.argtypes=[C.c_void_p,C.c_uint8,C.c_uint32,C.c_uint32,C.c_int16,C.c_int16,C.c_uint16,C.c_uint16,C.c_uint16,C.c_uint16,C.c_uint32,C.c_uint32,C.c_void_p];x.xcb_create_window_checked.restype=Cookie
        x.xcb_request_check.argtypes=[C.c_void_p,Cookie];x.xcb_request_check.restype=C.c_void_p
        for name in ('destroy','map','unmap'):
            fn=getattr(x,'xcb_'+name+'_window_checked');fn.argtypes=[C.c_void_p,C.c_uint32];fn.restype=Cookie
        x.xcb_configure_window_checked.argtypes=[C.c_void_p,C.c_uint32,C.c_uint16,C.c_void_p];x.xcb_configure_window_checked.restype=Cookie
        connection=x.xcb_connect(None,None)
        def checked(cookie):
            error=x.xcb_request_check(connection,cookie)
            assert not error,'XCB request failed'
        xid=x.xcb_generate_id(connection)
        def create():checked(x.xcb_create_window_checked(connection,0,xid,root,10,10,100,80,0,1,0,0,None))
        create()
        # Race initialization, not merely sequential reads of an existing token.
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            tokens=list(pool.map(lambda driver:driver.window_tokens([xid])[xid],[first,second]))
        assert tokens[0]==tokens[1] and len(tokens[0])==32,tokens
        original=tokens[0]
        checked(x.xcb_map_window_checked(connection,xid));checked(x.xcb_unmap_window_checked(connection,xid));checked(x.xcb_map_window_checked(connection,xid))
        values=(C.c_uint32*2)(30,40);checked(x.xcb_configure_window_checked(connection,xid,3,values))
        assert first.window_tokens([xid])[xid]==original
        checked(x.xcb_destroy_window_checked(connection,xid))
        assert first.window_tokens([xid])=={}
        create() # SAME numeric XID, SAME client connection/process.
        replacement=second.window_tokens([xid])[xid]
        assert replacement!=original
        run(['xprop','-id',str(xid),'-f','_LUDA_WINDOW_TOKEN','8s','-set','_LUDA_WINDOW_TOKEN','malformed'])
        try:
            first.window_tokens([xid]);raise AssertionError('malformed token accepted')
        except DesktopError as exc:assert exc.code=='INVALID_WINDOW_TOKEN',exc.code
        assert first.geometry(root)['width']==640 # finally released server grab
        # Force a real helper to stall after the XGrabServer has been processed.
        with tempfile.TemporaryDirectory() as directory:
            marker=Path(directory)/'grabbed'
            code='''from luda._x11_helper import _NativeX11\nfrom pathlib import Path\nimport time,sys\nx=_NativeX11()\noriginal=x.lib.XGetWindowProperty if hasattr(x.lib,"XGetWindowProperty") else None\ndef stall(*args):\n x.lib.XSync(x.display,False);Path(sys.argv[1]).write_text("grabbed");time.sleep(30);return original(*args)\nx.lib.XGetWindowProperty=stall\nx.window_tokens([x.root])\n'''
            try:
                run([sys.executable,'-c',code,str(marker)],timeout=.5)
                raise AssertionError('stalled helper did not time out')
            except DesktopError as exc:assert exc.code=='TIMEOUT',exc.code
            assert marker.read_text()=='grabbed'
            assert second.geometry(root)['height']==480
        print(json.dumps({'concurrent_initializers':'same token','move_and_remap':'token stable','same_xid_same_client_recreation':'new token','malformed_property':'rejected','exception_and_killed_helper':'server grab released'}))
finally:
    if connection:x.xcb_disconnect(connection)
    if p.poll() is None:p.terminate();p.wait(timeout=5)
