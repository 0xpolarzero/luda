"""Read client geometry in root pixels, avoiding window-manager frame offsets."""
import ctypes as C
from .common import DesktopError


_IGNORE_X_ERROR = C.CFUNCTYPE(C.c_int, C.c_void_p, C.c_void_p)(lambda *_: 0)


class X11:
    def __init__(self):
        x = self.lib = C.CDLL('libX11.so.6')
        x.XOpenDisplay.argtypes = [C.c_char_p]; x.XOpenDisplay.restype = C.c_void_p
        x.XDefaultRootWindow.argtypes = [C.c_void_p]; x.XDefaultRootWindow.restype = C.c_ulong
        x.XGetGeometry.argtypes = [C.c_void_p,C.c_ulong,C.POINTER(C.c_ulong),C.POINTER(C.c_int),C.POINTER(C.c_int),C.POINTER(C.c_uint),C.POINTER(C.c_uint),C.POINTER(C.c_uint),C.POINTER(C.c_uint)]
        x.XTranslateCoordinates.argtypes = [C.c_void_p,C.c_ulong,C.c_ulong,C.c_int,C.c_int,C.POINTER(C.c_int),C.POINTER(C.c_int),C.POINTER(C.c_ulong)]
        x.XCloseDisplay.argtypes = [C.c_void_p]
        # Windows can disappear between enumeration and geometry. Do not let Xlib exit the server.
        self.error_handler = _IGNORE_X_ERROR
        x.XSetErrorHandler.argtypes = [C.c_void_p]
        x.XSetErrorHandler(C.cast(self.error_handler, C.c_void_p))
        self.display = x.XOpenDisplay(None)
        if not self.display:
            raise DesktopError('DISPLAY_UNAVAILABLE', 'Cannot open DISPLAY; use the session launcher and run doctor.')
        self.root = x.XDefaultRootWindow(self.display)

    def geometry(self, window):
        root, child = C.c_ulong(), C.c_ulong()
        x, y = C.c_int(), C.c_int()
        w, h, border, depth = [C.c_uint() for _ in range(4)]
        if not self.lib.XGetGeometry(self.display, window, C.byref(root), C.byref(x), C.byref(y), C.byref(w), C.byref(h), C.byref(border), C.byref(depth)):
            raise DesktopError('STALE_TARGET', 'Window has disappeared.')
        if not self.lib.XTranslateCoordinates(self.display, window, self.root, 0, 0, C.byref(x), C.byref(y), C.byref(child)):
            raise DesktopError('STALE_TARGET', 'Cannot translate window coordinates.')
        return {'x':x.value,'y':y.value,'width':w.value,'height':h.value}

    def close(self):
        if self.display:
            self.lib.XCloseDisplay(self.display)
            self.display = None
