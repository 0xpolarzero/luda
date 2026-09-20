"""Kill a controller while its button is down on a private X server."""
import ctypes as C
import json
import os
import select
import signal
import subprocess
import sys
import time
from unittest.mock import patch
from luda._x11_helper import _NativeX11

reader,writer=os.pipe()
server=subprocess.Popen(['Xvfb','-displayfd',str(writer),'-screen','0','640x480x24','-nolisten','tcp'],pass_fds=(writer,),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
os.close(writer)
controller=None;native=None
try:
    assert select.select([reader],[],[],5)[0],'private X server did not start'
    display=':'+os.read(reader,32).decode().strip();os.close(reader);reader=None
    with patch.dict(os.environ,{'DISPLAY':display}):
        native=_NativeX11()
        fn=native.lib.XQueryPointer
        fn.argtypes=[C.c_void_p,C.c_ulong,C.POINTER(C.c_ulong),C.POINTER(C.c_ulong),C.POINTER(C.c_int),C.POINTER(C.c_int),C.POINTER(C.c_int),C.POINTER(C.c_int),C.POINTER(C.c_uint)]
        fn.restype=C.c_int
        def buttons():
            root,child=C.c_ulong(),C.c_ulong();coords=[C.c_int() for _ in range(4)];mask=C.c_uint()
            assert fn(native.display,native.root,C.byref(root),C.byref(child),*[C.byref(c) for c in coords],C.byref(mask))
            return mask.value&0x700
        assert buttons()==0
        source='from luda.input_guard import held_button\nimport time\nwith held_button("1"):\n print("held",flush=True)\n time.sleep(30)\n'
        controller=subprocess.Popen([sys.executable,'-c',source],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        assert select.select([controller.stdout],[],[],3)[0],'controller failed to hold input'
        assert controller.stdout.readline()==b'held\n'
        assert buttons()==0x100,'independent X pointer mask must show button down'
        began=time.monotonic();controller.kill();controller.wait(timeout=2)
        deadline=time.monotonic()+3
        while buttons()!=0 and time.monotonic()<deadline:time.sleep(.02)
        assert buttons()==0,'parent-death companion did not release button'
        print(json.dumps({'controller_killed_while_button_down':True,'independent_pointer_mask':0,'release_seconds':round(time.monotonic()-began,3)}))
finally:
    if controller:
        if controller.poll() is None:controller.kill();controller.wait(timeout=2)
        controller.stdout.close();controller.stderr.close()
    if native:native.close()
    if reader is not None:os.close(reader)
    server.terminate();server.wait(timeout=5)
