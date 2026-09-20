"""Independent cursor pixels/input/lifecycle checks on an owned private Xvfb."""
import ctypes as C
import os
import select
import subprocess
import time
from PIL import ImageGrab
from luda.cursor import Cursor
from luda._x11_helper import _NativeX11


def main():
    server = subprocess.Popen(['Xvfb','-displayfd','1','-screen','0','400x300x24','-nolisten','tcp'],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
    cursor = None
    native = None
    try:
        assert select.select([server.stdout],[],[],3)[0], 'Xvfb startup timed out'
        display = ':'+server.stdout.readline().decode().strip()
        os.environ['DISPLAY'] = display
        native = _NativeX11()
        x,d,root = native.lib,native.display,native.root
        x.XCreateSimpleWindow.argtypes=[C.c_void_p,C.c_ulong,C.c_int,C.c_int,C.c_uint,C.c_uint,C.c_uint,C.c_ulong,C.c_ulong]
        x.XCreateSimpleWindow.restype=C.c_ulong
        for name in ('XMapWindow','XDestroyWindow'):
            getattr(x,name).argtypes=[C.c_void_p,C.c_ulong]
        x.XSelectInput.argtypes=[C.c_void_p,C.c_ulong,C.c_long]
        x.XSetInputFocus.argtypes=[C.c_void_p,C.c_ulong,C.c_int,C.c_ulong]
        x.XGetInputFocus.argtypes=[C.c_void_p,C.POINTER(C.c_ulong),C.POINTER(C.c_int)]
        x.XWarpPointer.argtypes=[C.c_void_p,C.c_ulong,C.c_ulong,C.c_int,C.c_int,C.c_uint,C.c_uint,C.c_int,C.c_int]
        x.XQueryPointer.argtypes=[C.c_void_p,C.c_ulong,C.POINTER(C.c_ulong),C.POINTER(C.c_ulong)]+[C.POINTER(C.c_int)]*4+[C.POINTER(C.c_uint)]
        x.XSync.argtypes=[C.c_void_p,C.c_int]
        x.XPending.argtypes=[C.c_void_p]
        x.XNextEvent.argtypes=[C.c_void_p,C.c_void_p]
        target=x.XCreateSimpleWindow(d,root,0,0,400,300,0,0,0xffffff)
        x.XSelectInput(d,target,4)
        x.XMapWindow(d,target)
        x.XSetInputFocus(d,target,0,0)
        x.XWarpPointer(d,0,root,0,0,0,0,101,106)
        x.XSync(d,0)
        baseline=ImageGrab.grab(xdisplay=display).getpixel((101,106))
        cursor=Cursor()
        cursor.show(100,100)
        assert cursor.window_id is not None
        deadline=time.monotonic()+2
        while ImageGrab.grab(xdisplay=display).getpixel((101,106)) == baseline and time.monotonic()<deadline:
            time.sleep(.02)
        assert ImageGrab.grab(xdisplay=display).getpixel((101,106)) == (32,219,239), 'cursor must appear in desktop pixels'
        focus,revert=C.c_ulong(),C.c_int()
        x.XGetInputFocus(d,C.byref(focus),C.byref(revert))
        assert focus.value == target, 'overlay stole keyboard focus'
        returned_root,child=C.c_ulong(),C.c_ulong()
        coords=[C.c_int() for _ in range(4)]; mask=C.c_uint()
        x.XQueryPointer(d,root,C.byref(returned_root),C.byref(child),*[C.byref(v) for v in coords],C.byref(mask))
        assert [v.value for v in coords[:2]] == [101,106], 'overlay moved real pointer'
        assert child.value == target, 'overlay intercepted pointer hit testing'
        xt=C.CDLL('libXtst.so.6')
        xt.XTestFakeButtonEvent.argtypes=[C.c_void_p,C.c_uint,C.c_int,C.c_ulong]
        xt.XTestFakeButtonEvent(d,1,1,0);xt.XTestFakeButtonEvent(d,1,0,0);x.XSync(d,0)
        event=(C.c_long*24)()
        assert x.XPending(d)>0
        x.XNextEvent(d,C.byref(event))
        assert event[0] == 4 and event[4] == target, 'real click did not reach underlying app'
        cursor.hide()
        assert ImageGrab.grab(xdisplay=display).getpixel((101,106)) == baseline, 'hide returned before unmapping'
        cursor.show(100,100,'click')
        time.sleep(.1)
        assert ImageGrab.grab(xdisplay=display).getpixel((101,106)) != baseline
        time.sleep(1.6)
        assert ImageGrab.grab(xdisplay=display).getpixel((101,106)) == baseline, 'stale marker did not hide'
        process=cursor._process
        cursor.close()
        assert process.poll() == 0, 'EOF did not stop helper cleanly'
        cursor.show(100,100)
        assert cursor.window_id is not None, 'close should allow later restart'
        print('PASS: desktop pixels, focus, pointer, click-through, synchronous hide, stale hide, EOF cleanup, restart')
    finally:
        if cursor: cursor.close()
        if native: native.close()
        server.terminate();server.wait(timeout=3)


if __name__ == '__main__':
    main()
