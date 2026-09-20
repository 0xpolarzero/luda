"""Read client geometry in root pixels, avoiding window-manager frame offsets."""
import ctypes as C
import re
import secrets
from .common import DesktopError


_IGNORE_X_ERROR = C.CFUNCTYPE(C.c_int, C.c_void_p, C.c_void_p)(lambda *_: 0)


def _decode_window_token(actual_type, fmt, raw, remaining):
    if actual_type == 0:
        return None
    if actual_type != 31 or fmt != 8 or remaining or not re.fullmatch(b'[0-9a-f]{32}',raw):
        raise DesktopError('INVALID_WINDOW_TOKEN','Window generation property is malformed; no token was accepted.')
    return raw.decode('ascii')


def _decode_frame_extents(prop):
    actual,fmt,values,remaining=prop
    if actual!=6 or fmt!=32 or remaining or len(values)!=4 or any(v>65535 for v in values):
        raise DesktopError('INVALID_PROPERTY','Invalid bounded frame extents.')
    return dict(zip(('left','right','top','bottom'),values))


def _decode_wm_class(prop):
    actual,fmt,raw,remaining=prop
    if actual!=31 or fmt!=8 or remaining or len(raw)>1024:
        raise DesktopError('INVALID_PROPERTY','Invalid or oversized WM_CLASS.')
    parts=raw.split(b'\0')
    if len(parts)!=3 or parts[-1] or any(len(part)>512 for part in parts[:2]):
        raise DesktopError('INVALID_PROPERTY','WM_CLASS must contain two bounded strings.')
    result=[]
    for value in parts[:2]:
        try:result.append(value.decode('utf-8'))
        except UnicodeDecodeError:result.append(value.decode('latin-1'))
    return result


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

    def topology(self, unused=None):
        from ._randr import read_topology
        return {'server_generation': self.window_tokens([self.root])[self.root],
                'root': self.geometry(self.root), 'randr': read_topology(self)}

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

    def root_surface(self, window):
        """Return the root child containing a client (usually its WM frame)."""
        fn = self.lib.XQueryTree
        fn.argtypes = [C.c_void_p,C.c_ulong,C.POINTER(C.c_ulong),C.POINTER(C.c_ulong),C.POINTER(C.POINTER(C.c_ulong)),C.POINTER(C.c_uint)]
        fn.restype = C.c_int
        self.lib.XFree.argtypes = [C.c_void_p]
        visited = set()
        for _ in range(64):
            if window in visited or window == self.root:
                break
            visited.add(window)
            root,parent = C.c_ulong(),C.c_ulong()
            children = C.POINTER(C.c_ulong)(); count = C.c_uint()
            status = fn(self.display,window,C.byref(root),C.byref(parent),C.byref(children),C.byref(count))
            if children:self.lib.XFree(children)
            if not status:break
            if parent.value == self.root:return window
            window = parent.value
        raise DesktopError('STALE_TARGET','Cannot resolve the target root surface.')

    def cardinal(self, window, name):
        x = self.lib
        x.XInternAtom.argtypes = [C.c_void_p,C.c_char_p,C.c_int]; x.XInternAtom.restype = C.c_ulong
        x.XGetWindowProperty.argtypes = [C.c_void_p,C.c_ulong,C.c_ulong,C.c_long,C.c_long,C.c_int,C.c_ulong,C.POINTER(C.c_ulong),C.POINTER(C.c_int),C.POINTER(C.c_ulong),C.POINTER(C.c_ulong),C.POINTER(C.POINTER(C.c_ubyte))]
        x.XGetWindowProperty.restype = C.c_int
        x.XFree.argtypes = [C.c_void_p]
        atom = x.XInternAtom(self.display,name.encode(),True)
        if not atom: return None
        actual,nitems,remaining = C.c_ulong(),C.c_ulong(),C.c_ulong()
        fmt=C.c_int();data=C.POINTER(C.c_ubyte)()
        status=x.XGetWindowProperty(self.display,window,atom,0,1,False,0,C.byref(actual),C.byref(fmt),C.byref(nitems),C.byref(remaining),C.byref(data))
        try:
            return C.cast(data,C.POINTER(C.c_ulong))[0] if status == 0 and fmt.value == 32 and nitems.value == 1 and data else None
        finally:
            if data:x.XFree(data)

    def restack_above(self, pair):
        """Send an explicit-sibling configure request to the window manager.

        Managed clients have different frame parents, so a direct XConfigureWindow
        with the peer client can fail BadMatch before the WM receives it.
        """
        window,sibling=pair
        class Request(C.Structure):
            _fields_=[('type',C.c_int),('serial',C.c_ulong),('send_event',C.c_int),('display',C.c_void_p),('parent',C.c_ulong),('window',C.c_ulong),('x',C.c_int),('y',C.c_int),('width',C.c_int),('height',C.c_int),('border_width',C.c_int),('above',C.c_ulong),('detail',C.c_int),('value_mask',C.c_ulong)]
        class Event(C.Union):
            _fields_=[('request',Request),('pad',C.c_long*24)]
        event=Event();event.request.type=23;event.request.send_event=True
        event.request.display=self.display;event.request.parent=self.root
        event.request.window=window;event.request.above=sibling
        event.request.detail=0;event.request.value_mask=(1<<5)|(1<<6)
        x=self.lib
        x.XSendEvent.argtypes=[C.c_void_p,C.c_ulong,C.c_int,C.c_long,C.POINTER(Event)];x.XSendEvent.restype=C.c_int
        accepted=bool(x.XSendEvent(self.display,self.root,False,(1<<19)|(1<<20),C.byref(event)))
        x.XSync.argtypes=[C.c_void_p,C.c_int];x.XSync(self.display,False)
        return {'accepted':accepted}

    def selection_owner(self, selection):
        x=self.lib
        x.XInternAtom.argtypes=[C.c_void_p,C.c_char_p,C.c_int];x.XInternAtom.restype=C.c_ulong
        x.XGetSelectionOwner.argtypes=[C.c_void_p,C.c_ulong];x.XGetSelectionOwner.restype=C.c_ulong
        atom=x.XInternAtom(self.display,selection.encode('ascii'),True)
        return (x.XGetSelectionOwner(self.display,atom) or None) if atom else None

    def window_tokens(self, windows):
        """Initialize per-resource generation metadata atomically across clients."""
        x=self.lib
        x.XInternAtom.argtypes=[C.c_void_p,C.c_char_p,C.c_int];x.XInternAtom.restype=C.c_ulong
        x.XGetWindowProperty.argtypes=[C.c_void_p,C.c_ulong,C.c_ulong,C.c_long,C.c_long,C.c_int,C.c_ulong,C.POINTER(C.c_ulong),C.POINTER(C.c_int),C.POINTER(C.c_ulong),C.POINTER(C.c_ulong),C.POINTER(C.POINTER(C.c_ubyte))]
        x.XGetWindowProperty.restype=C.c_int
        x.XChangeProperty.argtypes=[C.c_void_p,C.c_ulong,C.c_ulong,C.c_ulong,C.c_int,C.c_int,C.POINTER(C.c_ubyte),C.c_int]
        x.XGrabServer.argtypes=[C.c_void_p];x.XUngrabServer.argtypes=[C.c_void_p]
        x.XSync.argtypes=[C.c_void_p,C.c_int];x.XFree.argtypes=[C.c_void_p]
        atom=x.XInternAtom(self.display,b'_LUDA_WINDOW_TOKEN',False)
        # Generate entropy before holding the server. Bound and deduplicate the
        # batch at the request boundary; never inspect arbitrary property data.
        candidates={xid:secrets.token_hex(16) for xid in windows}
        def read(xid):
            actual,nitems,remaining=C.c_ulong(),C.c_ulong(),C.c_ulong();fmt=C.c_int();data=C.POINTER(C.c_ubyte)()
            status=x.XGetWindowProperty(self.display,xid,atom,0,9,False,0,C.byref(actual),C.byref(fmt),C.byref(nitems),C.byref(remaining),C.byref(data))
            try:
                if status:raise DesktopError('STALE_TARGET','Window disappeared before generation read.')
                raw=C.string_at(data,min(nitems.value,36)) if data and fmt.value==8 else b''
                return _decode_window_token(actual.value,fmt.value,raw,remaining.value)
            finally:
                if data:x.XFree(data)
        result={}
        x.XGrabServer(self.display)
        try:
            # Validate every preexisting property before creating any new token.
            for xid in candidates:
                try:result[xid]=read(xid)
                except DesktopError as exc:
                    if exc.code!='STALE_TARGET':raise
            for xid,token in result.items():
                if token is None:
                    value=candidates[xid].encode('ascii')
                    buf=(C.c_ubyte*len(value)).from_buffer_copy(value)
                    x.XChangeProperty(self.display,xid,atom,31,8,0,buf,len(value))
                    token=read(xid)
                    if token!=candidates[xid]:
                        raise DesktopError('BACKEND_ERROR','Window generation initialization failed.')
                    result[xid]=token
            return result
        finally:
            # X server also releases the grab if timeout cancellation kills this
            # helper: it closes the owning connection. Flush the normal release.
            x.XUngrabServer(self.display)
            x.XSync(self.display,False)

    def _property(self, window, name, length):
        x=self.lib
        x.XInternAtom.argtypes=[C.c_void_p,C.c_char_p,C.c_int];x.XInternAtom.restype=C.c_ulong
        x.XGetWindowProperty.argtypes=[C.c_void_p,C.c_ulong,C.c_ulong,C.c_long,C.c_long,C.c_int,C.c_ulong,C.POINTER(C.c_ulong),C.POINTER(C.c_int),C.POINTER(C.c_ulong),C.POINTER(C.c_ulong),C.POINTER(C.POINTER(C.c_ubyte))]
        x.XGetWindowProperty.restype=C.c_int;x.XFree.argtypes=[C.c_void_p]
        if not hasattr(self,'_property_atoms'):self._property_atoms={}
        if name not in self._property_atoms:self._property_atoms[name]=x.XInternAtom(self.display,name.encode(),True)
        atom=self._property_atoms[name]
        if not atom:return None
        actual,nitems,remaining=C.c_ulong(),C.c_ulong(),C.c_ulong();fmt=C.c_int();data=C.POINTER(C.c_ubyte)()
        status=x.XGetWindowProperty(self.display,window,atom,0,length,False,0,C.byref(actual),C.byref(fmt),C.byref(nitems),C.byref(remaining),C.byref(data))
        try:
            if status:raise DesktopError('STALE_TARGET','Window disappeared while reading metadata.')
            if not actual.value:return None
            if fmt.value==32:
                values=list(C.cast(data,C.POINTER(C.c_ulong))[:min(nitems.value,length)]) if data else []
            else:
                values=C.string_at(data,min(nitems.value,length*4)) if data and fmt.value==8 else b''
            return actual.value,fmt.value,values,remaining.value
        finally:
            if data:x.XFree(data)

    def window_metadata(self, windows):
        requested=list(dict.fromkeys(windows));unavailable={};result={}
        def tokens(ids):
            try:return self.window_tokens(ids)
            except DesktopError as exc:
                if exc.code!='INVALID_WINDOW_TOKEN':raise
                valid={}
                for xid in ids:
                    try:valid.update(self.window_tokens([xid]))
                    except DesktopError as error:unavailable[xid]=error.code
                return valid
        before=tokens(requested)
        for xid in requested:
            if xid not in before:
                unavailable.setdefault(xid,'STALE_TARGET');continue
            try:
                item={'bounds':self.geometry(xid),'generation':before[xid],
                      'frame_extents':None,'wm_class':[],'pid':None,'unavailable_properties':[]}
                for name,key,length,decode in [('_NET_FRAME_EXTENTS','frame_extents',4,_decode_frame_extents),('WM_CLASS','wm_class',257,_decode_wm_class)]:
                    prop=self._property(xid,name,length)
                    if prop is None:item['unavailable_properties'].append({'property':name,'code':'MISSING_PROPERTY'})
                    else:
                        try:item[key]=decode(prop)
                        except DesktopError as error:item['unavailable_properties'].append({'property':name,'code':error.code})
                prop=self._property(xid,'_NET_WM_PID',1)
                if prop is not None and prop[0]==6 and prop[1]==32 and prop[3]==0 and len(prop[2])==1 and 0<prop[2][0]<=0x7fffffff:
                    item['pid']=prop[2][0]
                else:item['unavailable_properties'].append({'property':'_NET_WM_PID','code':'MISSING_PROPERTY' if prop is None else 'INVALID_PROPERTY'})
                result[xid]=item
            except DesktopError as exc:unavailable[xid]=exc.code
        after=tokens(list(result))
        for xid in list(result):
            if after.get(xid)!=before[xid]:
                unavailable.setdefault(xid,'STALE_TARGET');del result[xid]
        return {'windows':result,'unavailable':[{'xid':xid,'code':code} for xid,code in unavailable.items()],
                'requested_count':len(windows),'unique_requested_count':len(requested),
                'returned_count':len(result),'unavailable_count':len(unavailable)}

    def geometries(self, windows):
        result={}
        for xid in windows:
            try: result[xid]=self.geometry(xid)
            except DesktopError: pass
        return result

    def surface_at(self, point):
        child=C.c_ulong();x=C.c_int();y=C.c_int()
        if not self.lib.XTranslateCoordinates(self.display,self.root,self.root,point[0],point[1],C.byref(x),C.byref(y),C.byref(child)):
            raise DesktopError('DISPLAY_UNAVAILABLE','Cannot identify the pointer surface.')
        return child.value or None

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
                                     'override_redirect':True,'pid':self.cardinal(xid,'_NET_WM_PID'),'bounds':self.geometry(xid)})
                except DesktopError:
                    continue
        return surfaces


def main():
    import json
    import sys
    native = None
    try:
        request = json.loads(sys.stdin.buffer.read(65536))
        method = request['method']
        argument = request.get('argument')
        if method not in {'root','topology','selection_owner','restack_above','geometry','geometries','window_metadata','window_tokens','surface_at','root_surface','transient_for','children','popup_surfaces'}:
            raise DesktopError('INVALID_ARGUMENT','Unknown X11 metadata operation.')
        if method=='restack_above':
            if not isinstance(argument,list) or len(argument)!=2 or any(isinstance(v,bool) or not isinstance(v,int) or not 1<=v<=0xffffffff for v in argument) or argument[0]==argument[1]:
                raise DesktopError('INVALID_ARGUMENT','Restacking requires distinct target and sibling XIDs.')
        elif method=='selection_owner':
            if argument not in {'CLIPBOARD','PRIMARY'}:
                raise DesktopError('INVALID_ARGUMENT','Selection must be CLIPBOARD or PRIMARY.')
        elif method in {'geometries','window_metadata','window_tokens'}:
            if not isinstance(argument,list) or len(argument)>512 or any(isinstance(v,bool) or not isinstance(v,int) or not 1 <= v <= 0xffffffff for v in argument):
                raise DesktopError('INVALID_ARGUMENT','Invalid X11 metadata batch.')
        elif method == 'surface_at':
            if not isinstance(argument,list) or len(argument)!=2 or any(isinstance(v,bool) or not isinstance(v,int) or not -32768 <= v <= 32767 for v in argument):
                raise DesktopError('INVALID_ARGUMENT','Invalid surface point.')
        elif method not in ('root', 'topology') and (isinstance(argument,bool) or not isinstance(argument,int) or not 1 <= argument <= (4096 if method == 'popup_surfaces' else 0xffffffff)):
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
