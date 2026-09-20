"""Owned held-button worker; no parent press process can outlive cleanup."""
from contextlib import contextmanager
import json
import os
import selectors
import subprocess
import sys
from .common import DesktopError,checkpoint,mark_effect,run,subprocess_environment
from .keyboard import keyboard_recovery_checkpoint,_completion_proven,_retain_guardian
from .timing import elapsed_time
from .pointer_input import _move_pointer
from ._pointer_native import validate_position,validate_generation


class HeldPointer:
    def __init__(self,button,server_generation):
        self.button=button;self.server_generation=server_generation;self.active=True
    def move(self,x,y):
        if not self.active:raise DesktopError('STALE_TARGET','Held pointer context has ended.')
        return _move_pointer(x,y,self.server_generation,held_button=self.button)


@contextmanager
def held_button(button,server_generation=None,position=None,target=None):
    if button not in ('1','2','3'):
        raise DesktopError('INVALID_ARGUMENT','Unsupported held mouse button.')
    keyboard_recovery_checkpoint();checkpoint()
    if target is not None and (type(target) is not int or not 0<target<=0xffffffff):raise DesktopError('INVALID_ARGUMENT','Invalid native pointer target.')
    request={'button':button,'count':1,'target':target,'hold':True}
    if server_generation is not None:request['server_generation']=validate_generation(server_generation)
    if position is not None:request['position']=validate_position(position)
    plan=json.loads(run([sys.executable,'-m','luda._pointer_native','plan'],data=json.dumps(request).encode()+b'\n',timeout=2,max_output_bytes=4096))
    if plan.get('code'):raise DesktopError(plan['code'],plan['message'],effect=plan.get('effect','none'))
    child=subprocess.Popen([sys.executable,'-m','luda._keyboard_guard'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,start_new_session=True,env=subprocess_environment())
    output=b'';proven=False;retained=False;failure=None;result=None
    try:
        child.stdin.write(json.dumps(plan).encode()+b'\n');child.stdin.flush()
        with selectors.DefaultSelector() as watch:
            watch.register(child.stdout,selectors.EVENT_READ)
            deadline=elapsed_time()+3
            while b'\n' not in output:
                checkpoint()
                if elapsed_time()>deadline:raise DesktopError('TIMEOUT','Held input did not become ready.')
                if not watch.select(.025):continue
                chunk=os.read(child.stdout.fileno(),4096)
                if not chunk:raise DesktopError('INPUT_UNAVAILABLE','Held input companion ended before readiness.')
                output+=chunk
            line,output=output.split(b'\n',1);ready=json.loads(line)
            if not ready.get('held'):
                result=ready;proven=_completion_proven(result)
                raise DesktopError(result.get('code','INPUT_UNAVAILABLE'),result.get('message','Held input failed.'),effect=result.get('effect','none'))
            mark_effect()
            pointer=HeldPointer(button,plan['server_generation'])
            try:yield pointer
            except BaseException as exc:failure=exc
            finally:pointer.active=False
            try:child.stdin.write(b'D');child.stdin.flush()
            except BrokenPipeError:pass
            child.stdin.close()
            deadline=elapsed_time()+3.5
            while True:
                if elapsed_time()>deadline:raise DesktopError('INPUT_CLEANUP_PENDING','Held input cleanup remains pending.',effect='uncertain')
                if not watch.select(.025):continue
                chunk=os.read(child.stdout.fileno(),4096)
                if not chunk:break
                output+=chunk
                if len(output)>8192:raise DesktopError('INPUT_UNAVAILABLE','Held input response exceeded its bound.',effect='uncertain')
            child.wait(timeout=max(.01,deadline-elapsed_time()))
            result=json.loads(output.splitlines()[-1]);proven=_completion_proven(result)
            details={key:result[key] for key in ('cleanup_verified','session_changed','cleanup_skipped') if key in result}
            if failure:
                if isinstance(failure,DesktopError):failure.effect='uncertain';failure.details.update(details)
                raise failure
            if result.get('code'):raise DesktopError(result['code'],result['message'],effect=result.get('effect','uncertain'),details=details)
    except BaseException as exc:
        if not proven:
            mark_effect()
            if isinstance(exc,DesktopError):exc.effect='uncertain'
            if not child.stdin.closed:child.stdin.close()
            _retain_guardian(child,output,plan);retained=True
        if failure is not None and exc is not failure:
            if isinstance(failure,DesktopError):failure.effect='uncertain';failure.details['button_release_failed']=getattr(exc,'code','INPUT_UNAVAILABLE')
            raise failure from exc
        raise
    finally:
        if not child.stdin.closed:child.stdin.close()
        if not retained:child.stdout.close()
