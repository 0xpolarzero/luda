"""Kill a controller while its button is down on a private X server."""
import ctypes as C
import json
import os
import select
import signal
import subprocess
import sys
import time
import threading
from pathlib import Path
from live_keyboard_guard import descendants
# This suite specifically qualifies foreground compatibility device cleanup.
os.environ['LUDA_INPUT_ROUTE'] = 'shared'
from luda.common import DesktopError,checkpoint,operation_scope
from luda.input_guard import held_button
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
        guards=descendants(controller.pid);assert len(guards)==1
        injectors=descendants(guards[0]);assert len(injectors)==1
        os.kill(injectors[0],signal.SIGSTOP)
        began=time.monotonic();controller.kill();controller.wait(timeout=2)
        deadline=time.monotonic()+3
        while buttons()!=0 and time.monotonic()<deadline:time.sleep(.02)
        assert buttons()==0,'parent-death companion did not release button'
        assert not Path('/proc',str(injectors[0])).exists(),'injector must be reaped before release proof'
        cancelled=threading.Event();errors=[];held=threading.Event()
        def drag():
            try:
                with operation_scope(cancelled=cancelled),held_button('1'):
                    held.set()
                    while True:checkpoint();time.sleep(.01)
            except DesktopError as exc:errors.append(exc)
        worker=threading.Thread(target=drag);worker.start();assert held.wait(3);assert buttons()==0x100
        cancelled.set();worker.join(4)
        assert not worker.is_alive() and errors[0].code=='CANCELLED' and errors[0].details['cleanup_verified']
        assert buttons()==0
        subprocess.run(['xdotool','mousedown','1'],check=True)
        try:
            try:
                with held_button('1'):raise AssertionError('preheld accepted')
            except DesktopError as exc:assert exc.code=='INPUT_HELD'
            assert buttons()==0x100
        finally:subprocess.run(['xdotool','mouseup','1'],check=True)
        print(json.dumps({'controller_killed_while_button_down':True,'stopped_injector_reaped':True,'cancellation_release_verified':True,'preheld_input_preserved':True,'independent_pointer_mask':buttons()}))
finally:
    if controller:
        if controller.poll() is None:controller.kill();controller.wait(timeout=2)
        controller.stdout.close();controller.stderr.close()
    if native:native.close()
    if reader is not None:os.close(reader)
    server.terminate();server.wait(timeout=5)
