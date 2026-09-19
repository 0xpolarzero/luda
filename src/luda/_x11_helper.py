"""Read client geometry in root pixels, avoiding window-manager frame offsets."""
import ctypes as C
from .common import DesktopError


_IGNORE_X_ERROR = C.CFUNCTYPE(C.c_int, C.c_void_p, C.c_void_p)(lambda *_: 0)


class _NativeX11:
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

    def transient_for(self, window):
        """ICCCM owner hint, including managed dialogs; zero means no hint."""
        fn = self.lib.XGetTransientForHint
        fn.argtypes = [C.c_void_p, C.c_ulong, C.POINTER(C.c_ulong)]
        fn.restype = C.c_int
        owner = C.c_ulong()
        return owner.value if fn(self.display, window, C.byref(owner)) else None

    def children(self, window):
        fn = self.lib.XQueryTree
        fn.argtypes = [C.c_void_p,C.c_ulong,C.POINTER(C.c_ulong),C.POINTER(C.c_ulong),C.POINTER(C.POINTER(C.c_ulong)),C.POINTER(C.c_uint)]
        fn.restype = C.c_int
        self.lib.XFree.argtypes = [C.c_void_p]
        root,parent = C.c_ulong(),C.c_ulong()
        children = C.POINTER(C.c_ulong)(); count = C.c_uint()
        if not fn(self.display,window,C.byref(root),C.byref(parent),C.byref(children),C.byref(count)):
            return []
        try:
            return list(children[:count.value])
        finally:
            if children: self.lib.XFree(children)

    def popup_surfaces(self, limit=256):
        """Mapped override-redirect surfaces, not ordinary application windows.

        XIDs are observation-only: caller must resolve owner/process identity and
        revalidate before granting an opaque actionable target token.
        """
        class Attributes(C.Structure):
            _fields_ = [('x',C.c_int),('y',C.c_int),('width',C.c_int),('height',C.c_int),
                ('border_width',C.c_int),('depth',C.c_int),('visual',C.c_void_p),('root',C.c_ulong),
                ('class_',C.c_int),('bit_gravity',C.c_int),('win_gravity',C.c_int),('backing_store',C.c_int),
                ('backing_planes',C.c_ulong),('backing_pixel',C.c_ulong),('save_under',C.c_int),
                ('colormap',C.c_ulong),('map_installed',C.c_int),('map_state',C.c_int),
                ('all_event_masks',C.c_long),('your_event_mask',C.c_long),('do_not_propagate_mask',C.c_long),
                ('override_redirect',C.c_int),('screen',C.c_void_p)]
        fn = self.lib.XGetWindowAttributes
        fn.argtypes = [C.c_void_p,C.c_ulong,C.POINTER(Attributes)]; fn.restype = C.c_int
        surfaces = []
        # Popup menus normally are direct root children. Do not traverse arbitrary
        # application trees: it is unbounded and creates ambiguous nested targets.
        for xid in self.children(self.root)[:limit]:
            a = Attributes()
            if fn(self.display,xid,C.byref(a)) and a.map_state == 2 and a.override_redirect and a.class_ == 1:
                try:
                    surfaces.append({'xid':xid,'transient_for':self.transient_for(xid),
                                     'override_redirect':True,'bounds':self.geometry(xid)})
                except DesktopError:
                    continue
        return surfaces


def main():
    import json
    import sys
    native = None
    try:
        request = json.loads(sys.stdin.buffer.read(4096))
        method = request['method']
        argument = request.get('argument')
        if method not in {'root','geometry','transient_for','children','popup_surfaces'}:
            raise DesktopError('INVALID_ARGUMENT','Unknown X11 metadata operation.')
        if method != 'root' and (isinstance(argument,bool) or not isinstance(argument,int) or not 1 <= argument <= (4096 if method == 'popup_surfaces' else 0xffffffff)):
            raise DesktopError('INVALID_ARGUMENT','Invalid X11 metadata argument.')
        native = _NativeX11()
        result = native.root if method == 'root' else getattr(native,method)(argument)
        print(json.dumps({'result':result}))
    except DesktopError as exc:
        print(json.dumps({'error':{'code':exc.code,'message':str(exc)}}))
    except OSError:
        print(json.dumps({'error':{'code':'DEPENDENCY_MISSING','message':'Cannot load the native X11 library.'}}))
    except (ValueError,KeyError,TypeError):
        print(json.dumps({'error':{'code':'INVALID_ARGUMENT','message':'Malformed X11 metadata request.'}}))
    finally:
        if native is not None:
            native.close()


if __name__ == '__main__':
    main()
