"""Own injection worker; on controller EOF kill/wait it before key cleanup."""
import json
import os
import selectors
import subprocess
import sys
from .timing import elapsed_time


def emit(value):
    try:print(json.dumps(value),flush=True)
    except BrokenPipeError:pass


def release_owned(request,client):
    try:
        cleanup=subprocess.run([sys.executable,'-m','luda._keyboard_native','release'],
                               input=json.dumps({'keycodes':request['keycodes'],'client':client,'server_generation':request['server_generation']}).encode()+b'\n',
                               stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=2)
        value=json.loads(cleanup.stdout) if cleanup.returncode==0 else {}
        return {'cleanup_verified':value.get('released') is True,'session_changed':value.get('session_changed') is True,'cleanup_skipped':value.get('cleanup_skipped') is True}
    except Exception:
        return {'cleanup_verified':False,'session_changed':False,'cleanup_skipped':False}


def main():
    worker=None;armed=False;client=None;done=None;buffer=b'';partial=b'';request=None
    reason=None
    def consume(chunk,final=False):
        nonlocal armed,client,done,partial
        partial+=chunk
        lines=partial.split(b'\n')
        partial=lines.pop()
        if final and partial:lines.append(partial);partial=b''
        for line in lines:
            if not line:continue
            message=json.loads(line)
            if message.get('armed'):armed=True;client=message['client']
            elif message.get('done') or message.get('code'):done=message
    try:
        deadline=elapsed_time()+6
        with selectors.DefaultSelector() as watch:
            watch.register(sys.stdin.fileno(),selectors.EVENT_READ,'parent')
            initial=b''
            while b'\n' not in initial:
                if elapsed_time()>=deadline:raise ValueError()
                if not watch.select(.1):continue
                chunk=os.read(sys.stdin.fileno(),4096)
                if not chunk:return
                initial+=chunk
                if len(initial)>4096:raise ValueError()
            request=json.loads(initial)
            # No controller pipe is inherited by this owned worker.
            worker=subprocess.Popen([sys.executable,'-m','luda._keyboard_native','inject'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,start_new_session=True)
            worker.stdin.write(json.dumps(request).encode()+b'\n');worker.stdin.close()
            os.set_blocking(worker.stdout.fileno(),False)
            watch.register(worker.stdout,selectors.EVENT_READ,'worker')
            while True:
                if elapsed_time()>=deadline:reason='TIMEOUT';break
                for key,_ in watch.select(.05):
                    if key.data=='parent':
                        if not os.read(sys.stdin.fileno(),4096):reason='CANCELLED';break
                    else:
                        chunk=os.read(worker.stdout.fileno(),4096)
                        if chunk:buffer+=chunk;consume(chunk)
                        else:watch.unregister(worker.stdout)
                if len(buffer)>8192:reason='KEYBOARD_UNAVAILABLE';break
                if reason or worker.poll() is not None:break
        if worker.poll() is None:
            # SIGKILL is deliberate: there must be no injection request after
            # the cleanup helper starts, even if the worker is stuck in Xlib.
            worker.kill();worker.wait(timeout=1)
        while True:
            try:chunk=os.read(worker.stdout.fileno(),4096)
            except BlockingIOError:break
            if not chunk:break
            buffer+=chunk;consume(chunk)
            if len(buffer)>8192:break
        consume(b'',final=True)
        if armed and (reason or not done or not done.get('done')):
            cleaned=release_owned(request,client)
            result={'code':reason or 'KEYBOARD_INTERRUPTED','message':'Keyboard operation interrupted; owned key release was attempted. Inspect the application before retrying.','effect':'uncertain',**cleaned,'cleanup_request':{'keycodes':request['keycodes'],'client':client,'server_generation':request['server_generation']}}
        elif reason:
            result={'code':reason,'message':'Keyboard operation cancelled before key dispatch.','effect':'none'}
        else:
            result=done or {'code':'KEYBOARD_UNAVAILABLE','message':'Keyboard worker ended without a result.','effect':'none'}
        result['armed']=armed
        emit(result)
    except Exception:
        if worker and worker.poll() is None:
            worker.kill();worker.wait(timeout=1)
        if worker and worker.stdout:
            try:
                while True:
                    chunk=os.read(worker.stdout.fileno(),4096)
                    if not chunk:break
                    consume(chunk)
                consume(b'',final=True)
            except Exception:pass
        # Protocol errors are private implementation failures. A valid armed
        # record precedes every possible native event; conservatively clean the
        # validated plan if worker output was lost or malformed.
        cleaned=release_owned(request,client) if request and worker and armed else {'cleanup_verified':False}
        emit({'code':'KEYBOARD_UNAVAILABLE','message':'Keyboard companion failed; inspect state before retrying.',
              'effect':'uncertain' if worker else 'none','armed':bool(worker),**cleaned,
              'cleanup_request':{'keycodes':request['keycodes'],'client':client,'server_generation':request['server_generation']} if request and armed else None})
    finally:
        if worker and worker.stdout:worker.stdout.close()


if __name__=='__main__':main()
