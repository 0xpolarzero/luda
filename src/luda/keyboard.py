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
from .common import DesktopError, checkpoint, mark_effect, run, subprocess_environment, environment_scope
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
        raise DesktopError('BUSY','A previous input operation has unresolved cleanup; no new input sent.',details={'keyboard_recovery_pending':True})


def _completion_proven(result):
    return bool(result and (result.get('done') is True or result.get('cleanup_verified') is True or
                (result.get('session_changed') is True and result.get('cleanup_skipped') is True) or
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
                with _recovery_lock:
                    if token in _pending_recoveries:_pending_recoveries[token]['output']=output
                if len(output)>8192:raise ValueError()
            else:return
        guard.wait(timeout=max(.01,deadline-elapsed_time()))
        result=json.loads(output.splitlines()[-1])
        proven=_completion_proven(result)
        with _recovery_lock:
            if token in _pending_recoveries:_pending_recoveries[token]['cleanup_request']=result.get('cleanup_request')
    except Exception:
        pass
    finally:
        if guard.poll() is not None:guard.stdout.close()
        if proven:
            _resolve_recovery(token)
        # Unknown/failed cleanup retains its ownership token. Returning an error
        # must never reopen the input gate while an old injector can still act.


def _resolve_recovery(token):
    with _recovery_lock:record=_pending_recoveries.pop(token,None)
    if record and record['release']:record['release'](token)
    return record is not None


def _start_watcher(token,record):
    with _recovery_lock:
        if record.get('watcher') and record['watcher'].is_alive():return
        thread=threading.Thread(target=_recover_guardian,args=(token,record['guard'],record['output'],record['release']),daemon=True,name='luda-keyboard-recovery')
        record['watcher']=thread
        thread.start()


def _retain_guardian(guard,output,plan=None):
    token='keyboard:'+uuid.uuid4().hex
    record={'guard':guard,'output':output,'plan':plan,'environment':dict(subprocess_environment() or os.environ),
            'release':_release_recovery,'cleanup_request':None}
    with _recovery_lock:_pending_recoveries[token]=record
    if _retain_recovery:_retain_recovery(token)
    _start_watcher(token,record)


def recover_keyboard_input():
    """Retry owned cleanup only, in each interrupted command's original environment."""
    with _recovery_lock:records=list(_pending_recoveries.items())
    results=[];resolved=0;effect='none'
    for token,record in records:
        plan=record['plan']
        row={'resolved':False}
        if not plan or not plan.get('server_generation'):
            results.append({**row,'reason':'ownership_metadata_unavailable'});continue
        try:
            with environment_scope(record['environment']):
                proof=json.loads(run([sys.executable,'-m','luda._input_native'],
                    data=json.dumps({'operation':'check','server_generation':plan['server_generation']}).encode()+b'\n',timeout=2,max_output_bytes=4096))
                if proof.get('code'):
                    row['reason']=proof['code']
                elif proof.get('session_changed') and proof.get('cleanup_skipped'):
                    resolved+=int(_resolve_recovery(token));row.update(resolved=True,proof='original_server_replaced',cleanup_skipped=True)
                elif record['guard'].poll() is None:
                    os.kill(record['guard'].pid,signal.SIGCONT)
                    _start_watcher(token,record);row['reason']='guardian_still_recovering'
                elif record.get('cleanup_request') and record['cleanup_request'].get('server_generation')==plan['server_generation']:
                    effect='uncertain'
                    proof=json.loads(run([sys.executable,'-m','luda._pointer_native' if record['cleanup_request'].get('kind')=='pointer' else 'luda._keyboard_native','release'],
                        data=json.dumps(record['cleanup_request']).encode()+b'\n',timeout=2,max_output_bytes=4096,effect='uncertain'))
                    if proof.get('released') or (proof.get('session_changed') and proof.get('cleanup_skipped')):
                        resolved+=int(_resolve_recovery(token));row.update(resolved=True,proof='original_server_replaced' if proof.get('session_changed') else ('owned_buttons_released' if record['cleanup_request'].get('kind')=='pointer' else 'owned_keys_released'),cleanup_skipped=bool(proof.get('cleanup_skipped')))
                    else:row['reason']=proof.get('code','cleanup_not_verified')
                else:row['reason']='cleanup_metadata_not_available'
        except DesktopError as exc:
            if exc.code=='CANCELLED':raise
            row['reason']=exc.code
        except (ValueError,OSError,TypeError):row['reason']='cleanup_not_verified'
        results.append(row)
    with _recovery_lock:pending=len(_pending_recoveries)
    return {'effect':effect,'resolved_count':resolved,'pending_count':pending,'recoveries':results,
            'next_step':('Reconnect to the new desktop session, then observe again.' if any(row.get('proof')=='original_server_replaced' for row in results) else 'Observe again before acting.') if not pending else 'No input was replayed. Restore or restart the original desktop session, then retry input recovery; unresolved ownership stays blocked.'}


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
    return _dispatch_plan(plan)


def _dispatch_plan(plan):
    keyboard_recovery_checkpoint()
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
                    failure=DesktopError('TIMEOUT','Input companion deadline exceeded.');break
                if not ready.select(.025):continue
                chunk=os.read(guard.stdout.fileno(),4096)
                if not chunk:break
                output+=chunk
                if len(output)>8192:raise DesktopError('KEYBOARD_UNAVAILABLE','Input companion response exceeded its bound.',effect='uncertain')
        guard.stdin.close()
        # Closing the controller pipe asks the companion to stop its child
        # before cleanup. Never kill the companion during this cleanup period.
        cleanup_deadline=elapsed_time()+3.5
        with selectors.DefaultSelector() as cleanup:
            cleanup.register(guard.stdout,selectors.EVENT_READ)
            while True:
                remaining=cleanup_deadline-elapsed_time()
                if remaining<=0:
                    raise DesktopError('KEYBOARD_CLEANUP_PENDING','Input companion is still cleaning up; inspect state before more input.',effect='uncertain')
                if not cleanup.select(min(.05,remaining)):continue
                chunk=os.read(guard.stdout.fileno(),4096)
                if not chunk:break
                output+=chunk
                if len(output)>8192:raise DesktopError('KEYBOARD_UNAVAILABLE','Input companion response exceeded its bound.',effect='uncertain')
        guard.wait(timeout=max(.01,cleanup_deadline-elapsed_time()))
        if output:result=json.loads(output.splitlines()[-1])
        proven=_completion_proven(result)
        if result and result.get('armed'):mark_effect()
        if failure:
            if result and result.get('armed'):failure.effect='uncertain'
            if result:failure.details.update({k:result[k] for k in ('cleanup_verified','session_changed','cleanup_skipped') if k in result})
            raise failure
        if not result:raise DesktopError('KEYBOARD_UNAVAILABLE','Input companion returned no result.',effect='uncertain')
        if result.get('code'):
            raise DesktopError(result['code'],result['message'],effect=result.get('effect','uncertain'),details={k:result[k] for k in ('cleanup_verified','session_changed','cleanup_skipped') if k in result})
        return {'effect':'dispatched',**{key:result[key] for key in ('group_unchanged','locks_unchanged') if key in result},'verification':result.get('verification','Key delivery does not prove application outcome.')}
    except BaseException as exc:
        if not proven:
            mark_effect()
            if isinstance(exc,DesktopError):exc.effect='uncertain'
            if guard.stdin and not guard.stdin.closed:guard.stdin.close()
            _retain_guardian(guard,output,plan)
            retained=True
        raise
    finally:
        if guard.stdin and not guard.stdin.closed:guard.stdin.close()
        if not retained:guard.stdout.close()
