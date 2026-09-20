"""Private owned click/wheel injector; every event stays on one X connection."""
import ctypes as C
from contextlib import contextmanager
import json
import sys
import time
from ._keyboard_native import Keyboard,emit
from ._input_native import generation
from .common import DesktopError
from .input_validation import validate_position,validate_generation,validate_target_generation


def motion(native,position):
    with native.guard():
        x,y=validate_position(position)
        bounds=native.x.geometry(native.x.root)
        if x>=bounds['width'] or y>=bounds['height']:
            raise DesktopError('OUT_OF_BOUNDS','Pointer position is outside the current desktop.')
        native.test.XTestFakeMotionEvent.argtypes=[C.c_void_p,C.c_int,C.c_int,C.c_int,C.c_ulong]
        if not native.test.XTestFakeMotionEvent(native.x.display,-1,x,y,0):
            raise DesktopError('INPUT_UNAVAILABLE','Pointer movement failed.',effect='uncertain')
        native.x.lib.XSync(native.x.display,False)


@contextmanager
def target_guard(native,target,target_generation):
    with native.guard():
        if target is not None:
            native.target_token(target,target_generation)
            native.require_focus(target)
        yield


def check_held(native,owned=None):
    state=native.state();buttons=native.buttons()
    if native.pressed() or state.base_mods or (buttons!=[int(owned)] if owned else bool(buttons)):
        raise DesktopError('INPUT_HELD','Unexpected held input; pointer was not moved or pressed.')
    if state.latched_mods or state.latched_group:
        raise DesktopError('UNSUPPORTED_INPUT_STATE','Latched input; pointer was not moved or pressed.')


def move_pointer(native,request):
    expected=validate_generation(request.get('server_generation'))
    position=validate_position(request.get('position'))
    if generation(native.x)!=expected:
        raise DesktopError('SESSION_CHANGED','X server changed; pointer was not moved.')
    owned=request.get('held_button')
    if owned is not None and owned not in ('1','2','3'):
        raise DesktopError('INVALID_ARGUMENT','Invalid owned button.')
    target=request.get('target')
    token=validate_target_generation(target,request.get('target_generation'))
    if target is not None:token=native.target_token(target,token)
    with target_guard(native,target,token):
        check_held(native,owned)
        motion(native,position)
    return {'effect':'dispatched','server_generation':expected}


def plan_pointer(native,request):
    if request.get('button') not in ('1','2','3','4','5','6','7') or type(request.get('count')) is not int or not 1<=request['count']<=20:
        raise DesktopError('INVALID_ARGUMENT','Pointer button/count is unsupported.')
    current_generation=generation(native.x)
    if request.get('server_generation') is not None and validate_generation(request['server_generation'])!=current_generation:
        raise DesktopError('SESSION_CHANGED','X server changed before pointer planning.')
    position=validate_position(request['position']) if 'position' in request else None
    if position is not None:
        bounds=native.x.geometry(native.x.root)
        if position[0]>=bounds['width'] or position[1]>=bounds['height']:raise DesktopError('OUT_OF_BOUNDS','Pointer position is outside the current desktop.')
    target=request.get('target')
    if target is not None and (type(target) is not int or not 0<target<=0xffffffff):
        raise DesktopError('INVALID_ARGUMENT','Invalid pointer target.')
    token=validate_target_generation(target,request.get('target_generation'))
    if target is not None:token=native.target_token(target,token)
    state=native.state()
    if native.pressed() or native.buttons() or state.base_mods:
        raise DesktopError('INPUT_HELD','Keys or pointer buttons are already held; no click or scroll sent.')
    if state.latched_mods or state.latched_group:
        raise DesktopError('UNSUPPORTED_INPUT_STATE','Latched keyboard state is active; no click or scroll sent.')
    if target is not None:
        native.require_focus(target)
    return {'input_route':getattr(native.private,'route','private'),'kind':'pointer','button':request['button'],'count':request['count'],'target':target,'server_generation':current_generation,**({'target_generation':token} if token is not None else {}),**({'position':position} if position is not None else {}),**({'hold':True} if request.get('hold') is True else {})}


def event(native,button,pressed):
    with native.guard():
        native.test.XTestFakeButtonEvent.argtypes=[C.c_void_p,C.c_uint,C.c_int,C.c_ulong]
        if not native.test.XTestFakeButtonEvent(native.x.display,int(button),pressed,0):
            raise DesktopError('INPUT_UNAVAILABLE','Pointer dispatch failed.',effect='uncertain')
        native.x.lib.XSync(native.x.display,False)


def main():
    native=None
    try:
        request=json.loads(sys.stdin.buffer.readline(4097))
        if sys.argv[1]=='release':
            from ._private_cleanup import ended_ownership
            receipt=ended_ownership(request)
            if receipt is not None:
                emit(receipt);return
        native=Keyboard()
        if sys.argv[1]=='plan':emit(plan_pointer(native,request))
        elif sys.argv[1]=='move':emit(move_pointer(native,request))
        elif sys.argv[1]=='release':
            if request.get('button') not in ('1','2','3','4','5','6','7'):raise ValueError()
            if generation(native.x)!=request['server_generation']:
                emit({'released':False,'session_changed':True,'cleanup_skipped':True});return
            native.disconnect_injector(request['client'])
            event(native,request['button'],False)
            emit({'released':int(request['button']) not in native.buttons()})
        elif sys.argv[1]=='inject':
            if generation(native.x)!=request['server_generation']:
                raise DesktopError('SESSION_CHANGED','X server changed before pointer input.')
            if plan_pointer(native,request)!=request:
                raise DesktopError('INPUT_STATE_CHANGED','Pointer plan changed; no click or scroll sent.')
            emit({'armed':True,'client':native.client_resource()})
            pressed=False
            try:
                for index in range(request['count']):
                    with target_guard(native,request.get('target'),request.get('target_generation')):
                        check_held(native)
                        if index==0 and 'position' in request:motion(native,request['position'])
                        pressed=True;event(native,request['button'],True)
                    if request.get('hold'):
                        emit({'held':True})
                        time.sleep(60)
                        raise DesktopError('TIMEOUT','Held button exceeded lifetime.',effect='uncertain')
                    time.sleep(.012)
                    event(native,request['button'],False);pressed=False
                    if index+1<request['count']:time.sleep(.035)
            finally:
                if pressed:event(native,request['button'],False)
            if int(request['button']) in native.buttons():
                raise DesktopError('INPUT_RELEASE_UNVERIFIED','Pointer button release was not verified.',effect='uncertain')
            emit({'done':True,'effect':'dispatched','verification':'Pointer delivery does not prove application outcome.'})
        else:raise ValueError()
    except DesktopError as exc:emit({'code':exc.code,'message':str(exc),'effect':exc.effect})
    except Exception:emit({'code':'INPUT_UNAVAILABLE','message':'Native pointer helper failed.','effect':'uncertain' if sys.argv[1]=='move' else 'none'})
    finally:
        if native:native.close()


if __name__=='__main__':main()
