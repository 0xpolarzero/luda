"""Bounded one-shot clicks/wheels with supervised owned-button release."""
import json
import sys
from .input_validation import validate_position,validate_generation,validate_target_generation
from .common import DesktopError,run
from .keyboard import _dispatch_plan,keyboard_recovery_checkpoint


def click_button(button,count=1,target=None,position=None,server_generation=None,target_generation=None):
    if button not in ('1','2','3','4','5','6','7') or type(count) is not int or not 1<=count<=20:
        raise DesktopError('INVALID_ARGUMENT','Expected pointer button 1–7 and count 1–20.')
    if target is not None and (type(target) is not int or not 0<target<=0xffffffff):
        raise DesktopError('INVALID_ARGUMENT','Invalid native pointer target.')
    keyboard_recovery_checkpoint()
    validate_target_generation(target,target_generation)
    request={'button':button,'count':count,'target':target}
    if target_generation is not None:request['target_generation']=target_generation
    if position is not None:request['position']=validate_position(position)
    if server_generation is not None:request['server_generation']=validate_generation(server_generation)
    plan=json.loads(run([sys.executable,'-m','luda._pointer_native','plan'],data=json.dumps(request).encode()+b'\n',timeout=2,max_output_bytes=4096))
    if plan.get('code'):raise DesktopError(plan['code'],plan['message'],effect=plan.get('effect','none'))
    return _dispatch_plan(plan)


def check_pointer_ready(target=None,target_generation=None):
    """Refuse existing held input before a caller's initial pointer movement."""
    if target is not None and (type(target) is not int or not 0<target<=0xffffffff):
        raise DesktopError('INVALID_ARGUMENT','Invalid native pointer target.')
    keyboard_recovery_checkpoint()
    validate_target_generation(target,target_generation)
    request={'button':'1','count':1,'target':target}
    if target_generation is not None:request['target_generation']=target_generation
    result=json.loads(run([sys.executable,'-m','luda._pointer_native','plan'],data=json.dumps(request).encode()+b'\n',timeout=2,max_output_bytes=4096))
    if result.get('code'):raise DesktopError(result['code'],result['message'],effect=result.get('effect','none'))
    return {'effect':'none','ready':True,'server_generation':result['server_generation']}


def move_pointer(x,y,server_generation,target=None,target_generation=None):
    """Move without held buttons, bound to the preflight's original server."""
    return _move_pointer(x,y,server_generation,target=target,target_generation=target_generation)


def _move_pointer(x,y,server_generation,target=None,held_button=None,target_generation=None):
    position=validate_position((x,y));validate_generation(server_generation)
    if target is not None and (type(target) is not int or not 0<target<=0xffffffff):
        raise DesktopError('INVALID_ARGUMENT','Invalid native pointer target.')
    keyboard_recovery_checkpoint()
    validate_target_generation(target,target_generation)
    request={'position':position,'server_generation':server_generation,'target':target,'held_button':held_button}
    if target_generation is not None:request['target_generation']=target_generation
    result=json.loads(run([sys.executable,'-m','luda._pointer_native','move'],data=json.dumps(request).encode()+b'\n',timeout=2,max_output_bytes=4096,effect='uncertain'))
    if result.get('code'):raise DesktopError(result['code'],result['message'],effect=result.get('effect','none'))
    return result
