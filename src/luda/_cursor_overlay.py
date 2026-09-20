"""Private X11 cursor renderer. Pipe EOF exits; stale feedback unmaps itself."""
import ctypes as C
import os
import select
import time

from ._x11_helper import _NativeX11


class Rectangle(C.Structure):
    _fields_ = [('x', C.c_short), ('y', C.c_short), ('width', C.c_ushort), ('height', C.c_ushort)]


class Attributes(C.Structure):
    _fields_ = [('background_pixmap', C.c_ulong), ('background_pixel', C.c_ulong),
                ('border_pixmap', C.c_ulong), ('border_pixel', C.c_ulong),
                ('bit_gravity', C.c_int), ('win_gravity', C.c_int),
                ('backing_store', C.c_int), ('backing_planes', C.c_ulong),
                ('backing_pixel', C.c_ulong), ('save_under', C.c_int),
                ('event_mask', C.c_long), ('do_not_propagate_mask', C.c_long),
                ('override_redirect', C.c_int), ('colormap', C.c_ulong), ('cursor', C.c_ulong)]


class Overlay:
    def __init__(self):
        self.native = _NativeX11()
        x, d = self.native.lib, self.native.display
        self.x, self.d = x, d
        x.XCreateSimpleWindow.argtypes = [C.c_void_p,C.c_ulong,C.c_int,C.c_int,C.c_uint,C.c_uint,C.c_uint,C.c_ulong,C.c_ulong]
        x.XCreateSimpleWindow.restype = C.c_ulong
        x.XChangeWindowAttributes.argtypes = [C.c_void_p,C.c_ulong,C.c_ulong,C.POINTER(Attributes)]
        x.XCreateGC.argtypes = [C.c_void_p,C.c_ulong,C.c_ulong,C.c_void_p]
        x.XCreateGC.restype = C.c_void_p
        x.XSetForeground.argtypes = [C.c_void_p,C.c_void_p,C.c_ulong]
        x.XFillRectangles.argtypes = [C.c_void_p,C.c_ulong,C.c_void_p,C.POINTER(Rectangle),C.c_int]
        x.XMoveWindow.argtypes = [C.c_void_p,C.c_ulong,C.c_int,C.c_int]
        for name in ('XMapRaised', 'XUnmapWindow', 'XDestroyWindow'):
            getattr(x, name).argtypes = [C.c_void_p,C.c_ulong]
        x.XFreeGC.argtypes = [C.c_void_p,C.c_void_p]
        x.XSync.argtypes = [C.c_void_p,C.c_int]
        self.shape = C.CDLL('libXext.so.6')
        self.shape.XShapeQueryExtension.argtypes = [C.c_void_p,C.POINTER(C.c_int),C.POINTER(C.c_int)]
        event, error = C.c_int(), C.c_int()
        if not self.shape.XShapeQueryExtension(d,C.byref(event),C.byref(error)):
            raise RuntimeError('SHAPE unavailable')
        self.shape.XShapeQueryVersion.argtypes = [C.c_void_p,C.POINTER(C.c_int),C.POINTER(C.c_int)]
        major, minor = C.c_int(), C.c_int()
        if not self.shape.XShapeQueryVersion(d,C.byref(major),C.byref(minor)) or (major.value,minor.value) < (1,1):
            raise RuntimeError('SHAPE input regions unavailable')
        self.shape.XShapeCombineRectangles.argtypes = [C.c_void_p,C.c_ulong,C.c_int,C.c_int,C.c_int,C.POINTER(Rectangle),C.c_int,C.c_int,C.c_int]
        self.window = x.XCreateSimpleWindow(d,self.native.root,0,0,48,48,0,0,0)
        attributes = Attributes(override_redirect=1)
        x.XChangeWindowAttributes(d,self.window,1 << 9,C.byref(attributes))
        # An empty input shape lets both core and extension pointer events pass through.
        self.shape.XShapeCombineRectangles(d,self.window,2,0,0,None,0,0,0)
        self.gc = x.XCreateGC(d,self.window,0,None)
        x.XSync(d,0)

    def show(self, x, y, action):
        outer, inner = [], []
        for row in range(25):
            left, width = (12, 1 + row * 3 // 5) if row < 19 else (18, 5)
            outer.append((left,12+row,width,1))
            if width > 2 and row > 1 and row < 24:
                inner.append((left+1,12+row,width-2,1))
        if action:
            for row in range(-10,11):
                for col in range(-10,11):
                    if 64 <= row*row+col*col <= 100:
                        outer.append((12+col,12+row,1,1))
                        inner.append((12+col,12+row,1,1))
        bounds = (Rectangle * len(outer))(*(Rectangle(*r) for r in outer))
        fill = (Rectangle * len(inner))(*(Rectangle(*r) for r in inner))
        self.shape.XShapeCombineRectangles(self.d,self.window,0,0,0,bounds,len(bounds),0,0)
        self.x.XMoveWindow(self.d,self.window,x-12,y-12)
        self.x.XMapRaised(self.d,self.window)
        self.x.XSetForeground(self.d,self.gc,0x18202a)
        self.x.XFillRectangles(self.d,self.window,self.gc,bounds,len(bounds))
        self.x.XSetForeground(self.d,self.gc,0xff55aa if action else 0x20dbef)
        self.x.XFillRectangles(self.d,self.window,self.gc,fill,len(fill))
        self.x.XSync(self.d,0)

    def hide(self):
        self.x.XUnmapWindow(self.d,self.window)
        self.x.XSync(self.d,0)

    def close(self):
        self.x.XFreeGC(self.d,self.gc)
        self.x.XDestroyWindow(self.d,self.window)
        self.native.close()


def main():
    overlay = Overlay()
    try:
        os.write(1,f'{overlay.window}\n'.encode())
        pending = b''
        deadline = None
        while True:
            timeout = None if deadline is None else max(0,deadline-time.monotonic())
            if not select.select([0],[],[],timeout)[0]:
                overlay.hide()
                deadline = None
                continue
            chunk = os.read(0,4096)
            if not chunk:
                return
            pending += chunk
            if len(pending) > 8192:
                return
            while b'\n' in pending:
                line,pending = pending.split(b'\n',1)
                if line == b'hide':
                    overlay.hide()
                    os.write(1,b'hidden\n')
                    deadline = None
                else:
                    a,b,action = map(int,line.split())
                    if not (-32768 <= a <= 32767 and -32768 <= b <= 32767 and action in (0,1)):
                        return
                    overlay.show(a,b,action)
                    deadline = time.monotonic()+1.5
    finally:
        overlay.close()


if __name__ == '__main__':
    main()
