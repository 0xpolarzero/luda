"""Validated named chords with isolated XKB planning and crash-safe ownership."""
import json
import os
import re
import selectors
import subprocess
import sys
import signal
import threading
import uuid
from .common import DesktopError, checkpoint, mark_effect, run, subprocess_environment
from .timing import elapsed_time


_recovery_lock=threading.Lock()
_pending_recoveries={}
_retain_recovery=None
_release_recovery=None


def set_recovery_hooks(retain,release):
    """MCP registers synchronous quarantine ownership callbacks at startup."""
    global _retain_recovery,_release_recovery
    _retain_recovery,_release_recovery=retain,release


def keyboard_recovery_checkpoint():
    with _recovery_lock:
        pending=bool(_pending_recoveries)
    if pending:
        raise DesktopError('BUSY','A previous keyboard operation has unresolved cleanup; no new input sent.',details={'keyboard_recovery_pending':True})


def _completion_proven(result):
    return bool(result and (result.get('done') is True or result.get('cleanup_verified') is True or
                (result.get('armed') is False and result.get('effect')=='none')))


def _recover_guardian(token,guard,output,release):
    proven=False
    try:
        if guard.poll() is None:
            # Resume only our unreaped child. A stopped companion must be able
            # to kill/wait its injector and complete its own bounded cleanup.
            os.kill(guard.pid,signal.SIGCONT)
        deadline=elapsed_time()+12
        with selectors.DefaultSelector() as ready:
            ready.register(guard.stdout,selectors.EVENT_READ)
            while elapsed_time()<deadline:
                if not ready.select(.05):continue
                chunk=os.read(guard.stdout.fileno(),4096)
                if not chunk:break
                output+=chunk
                if len(output)>8192:raise ValueError()
            else:return
        guard.wait(timeout=max(.01,deadline-elapsed_time()))
        proven=_completion_proven(json.loads(output))
    except Exception:
        pass
    finally:
        if guard.poll() is not None:guard.stdout.close()
        if proven:
            with _recovery_lock:_pending_recoveries.pop(token,None)
            if release:release(token)
        # Unknown/failed cleanup retains its ownership token. Returning an error
        # must never reopen the input gate while an old injector can still act.


def _retain_guardian(guard,output):
    token='keyboard:'+uuid.uuid4().hex
    with _recovery_lock:_pending_recoveries[token]=guard
    if _retain_recovery:_retain_recovery(token)
    thread=threading.Thread(target=_recover_guardian,args=(token,guard,output,_release_recovery),daemon=True,name='luda-keyboard-recovery')
    thread.start()


def validate_chord(chord):
    if not isinstance(chord,str) or not 1<=len(chord)<=64:
        raise DesktopError('INVALID_KEY','Supply one named key chord, such as ctrl+s, Return or Escape.')
    parts=chord.split('+')
    modifiers={'ctrl','alt','shift','super'}
    named={'Return','Tab','Escape','BackSpace','Delete','Home','End','Left','Right','Up','Down','Page_Up','Page_Down','Insert','space'}
    if any(p not in modifiers for p in parts[:-1]) or len(set(parts[:-1]))!=len(parts[:-1]) or not (parts[-1] in named or re.fullmatch(r'[A-Za-z0-9]|F(?:[1-9]|1[0-9]|2[0-4])',parts[-1])):
        raise DesktopError('INVALID_KEY','Use one named key with optional ctrl, alt, shift or super. Text belongs in desktop_type.')
    return parts


def keyboard_capabilities():
    try:
        result=json.loads(run([sys.executable,'-m','luda._keyboard_native','probe'],data=b'{}\n',timeout=2,max_output_bytes=4096))
        if not isinstance(result,dict):
            return {'available':False,'reason':'invalid_response'}
        if result.get('code'):
            return {'available':False,'reason':result['code']}
        if result.get('available') is not True:
            return {'available':False,'reason':'invalid_response'}
        return result
    except DesktopError as exc:
        if exc.code in ('TIMEOUT','CANCELLED'):raise
        return {'available':False,'reason':exc.code}
    except (ValueError,TypeError):
        return {'available':False,'reason':'invalid_response'}


def send_chord(chord,target):
    validate_chord(chord)
    keyboard_recovery_checkpoint()
    if type(target) is not int or not 0<target<=0xffffffff:
        raise DesktopError('INVALID_ARGUMENT','Invalid native target window.')
    request={'chord':chord,'target':target}
    plan=json.loads(run([sys.executable,'-m','luda._keyboard_native','plan'],data=json.dumps(request).encode()+b'\n',timeout=2,max_output_bytes=4096))
    if plan.get('code'):raise DesktopError(plan['code'],plan['message'])
    checkpoint()
    guard=subprocess.Popen([sys.executable,'-m','luda._keyboard_guard'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,start_new_session=True,env=subprocess_environment())
    failure=None;output=b'';result=None;retained=False;proven=False
    try:
        guard.stdin.write(json.dumps(plan).encode()+b'\n');guard.stdin.flush()
        with selectors.DefaultSelector() as ready:
            ready.register(guard.stdout,selectors.EVENT_READ)
            deadline=elapsed_time()+7
            while b'\n' not in output:
                try:checkpoint()
                except DesktopError as exc:
                    failure=exc;break
                if elapsed_time()>=deadline:
                    failure=DesktopError('TIMEOUT','Keyboard companion deadline exceeded.');break
                if not ready.select(.025):continue
                chunk=os.read(guard.stdout.fileno(),4096)
                if not chunk:break
                output+=chunk
                if len(output)>8192:raise DesktopError('KEYBOARD_UNAVAILABLE','Keyboard companion response exceeded its bound.',effect='uncertain')
        guard.stdin.close()
        # Closing the controller pipe asks the companion to stop its child
        # before cleanup. Never kill the companion during this cleanup period.
        cleanup_deadline=elapsed_time()+3.5
        with selectors.DefaultSelector() as cleanup:
            cleanup.register(guard.stdout,selectors.EVENT_READ)
            while True:
                remaining=cleanup_deadline-elapsed_time()
                if remaining<=0:
                    raise DesktopError('KEYBOARD_CLEANUP_PENDING','Keyboard companion is still cleaning up; inspect state before more input.',effect='uncertain')
                if not cleanup.select(min(.05,remaining)):continue
                chunk=os.read(guard.stdout.fileno(),4096)
                if not chunk:break
                output+=chunk
                if len(output)>8192:raise DesktopError('KEYBOARD_UNAVAILABLE','Keyboard companion response exceeded its bound.',effect='uncertain')
        guard.wait(timeout=max(.01,cleanup_deadline-elapsed_time()))
        if output:result=json.loads(output)
        proven=_completion_proven(result)
        if result and result.get('armed'):mark_effect()
        if failure:
            if result and result.get('armed'):failure.effect='uncertain'
            if result and 'cleanup_verified' in result:failure.details['cleanup_verified']=result['cleanup_verified']
            raise failure
        if not result:raise DesktopError('KEYBOARD_UNAVAILABLE','Keyboard companion returned no result.',effect='uncertain')
        if result.get('code'):
            raise DesktopError(result['code'],result['message'],effect=result.get('effect','uncertain'),details={k:result[k] for k in ('cleanup_verified',) if k in result})
        return {'effect':'dispatched','group_unchanged':result['group_unchanged'],'locks_unchanged':result['locks_unchanged'],'verification':'Key delivery does not prove application outcome.'}
    except BaseException as exc:
        if not proven:
            mark_effect()
            if isinstance(exc,DesktopError):exc.effect='uncertain'
            if guard.stdin and not guard.stdin.closed:guard.stdin.close()
            _retain_guardian(guard,output)
            retained=True
        raise
    finally:
        if guard.stdin and not guard.stdin.closed:guard.stdin.close()
        if not retained:guard.stdout.close()
