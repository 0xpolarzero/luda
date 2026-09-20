"""Generation-bound pointer events on one isolated native X connection."""
import ctypes as C
import json
import sys
from ._x11_helper import _NativeX11
from .common import DesktopError


def generation(native):
    return native.window_tokens([native.root])[native.root]


def main():
    native=None
    try:
        request=json.loads(sys.stdin.buffer.readline(4097));native=_NativeX11()
        current=generation(native)
        if request['operation']=='generation':
            result={'server_generation':current}
        elif request['operation']=='check':
            result={'session_changed':current!=request['server_generation'],'cleanup_skipped':current!=request['server_generation']}
        elif request['operation'] in ('press','release'):
            if request.get('button') not in ('1','2','3','4','5','6','7'):
                raise DesktopError('INVALID_ARGUMENT','Unsupported pointer button.')
            if current!=request['server_generation']:
                if request['operation']=='press':raise DesktopError('SESSION_CHANGED','X server changed before input; no input sent.')
                result={'released':False,'session_changed':True,'cleanup_skipped':True}
            else:
                test=C.CDLL('libXtst.so.6');test.XTestFakeButtonEvent.argtypes=[C.c_void_p,C.c_uint,C.c_int,C.c_ulong]
                native.lib.XSync.argtypes=[C.c_void_p,C.c_int]
                if not test.XTestFakeButtonEvent(native.display,int(request['button']),request['operation']=='press',0):
                    raise DesktopError('INPUT_UNAVAILABLE','XTest pointer dispatch failed.',effect='uncertain')
                native.lib.XSync(native.display,False)
                released=request['operation']=='release'
                if released and int(request['button'])<=5:
                    native.lib.XQueryPointer.argtypes=[C.c_void_p,C.c_ulong,C.POINTER(C.c_ulong),C.POINTER(C.c_ulong)]+[C.POINTER(C.c_int)]*4+[C.POINTER(C.c_uint)]
                    root,child=C.c_ulong(),C.c_ulong();coordinates=[C.c_int() for _ in range(4)];mask=C.c_uint()
                    okay=native.lib.XQueryPointer(native.display,native.root,C.byref(root),C.byref(child),*[C.byref(value) for value in coordinates],C.byref(mask))
                    released=bool(okay and not mask.value&(1<<(7+int(request['button']))))
                result={'released':released,'pressed':request['operation']=='press','session_changed':False}
        else:raise DesktopError('INVALID_ARGUMENT','Invalid input helper operation.')
        print(json.dumps(result),flush=True)
    except DesktopError as exc:print(json.dumps({'code':exc.code,'message':str(exc),'effect':exc.effect}),flush=True)
    except Exception:print(json.dumps({'code':'INPUT_UNAVAILABLE','message':'Native input helper failed.','effect':'none'}),flush=True)
    finally:
        if native:native.close()


if __name__=='__main__':main()
