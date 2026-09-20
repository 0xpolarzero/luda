"""Real XID reuse and competing-client exclusion during owned disconnect."""
import json
import os
from pathlib import Path
import select
import subprocess
import sys
import tempfile
import time
from luda._keyboard_native import Keyboard
from luda.common import stop_process


def until(predicate,timeout=5):
    end=time.monotonic()+timeout
    while time.monotonic()<end:
        if predicate():return
        time.sleep(.005)
    raise AssertionError('Owned client did not reach barrier')


def child_mode():
    keyboard=Keyboard()
    try:
        if sys.argv[1]=='--client':
            resource=keyboard.client_resource();print(json.dumps(resource),flush=True)
            for line in sys.stdin:
                if line.strip()=='ping':
                    keyboard.x.geometry(resource['xid']);print('alive',flush=True)
                else:break
        else:
            resource=json.loads(sys.argv[2]);base=Path(sys.argv[3]);original=keyboard.x._property
            def barrier(*args):
                value=original(*args)
                (base/'entered').write_text('nonce read under grab')
                until(lambda:(base/'continue').exists())
                return value
            keyboard.x._property=barrier
            keyboard.disconnect_injector(resource)
    finally:keyboard.close()


def main():
    if os.getuid()==0 or os.environ.get('LUDA_ISOLATED_TEST_DISPLAY')!='1':raise SystemExit('Private ordinary-user display required')
    keyboard=Keyboard();children=[];results=[]
    def client():
        p=subprocess.Popen([sys.executable,__file__,'--client'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
        children.append(p);return p
    def read(p):
        assert select.select([p.stdout],[],[],5)[0]
        line=p.stdout.readline();assert line,('client exited',p.poll())
        return line.strip()
    def ping(p):p.stdin.write('ping\n');p.stdin.flush();assert read(p)=='alive'
    try:
        original=client();old=json.loads(read(original));stop_process(original)
        replacement=client();new=json.loads(read(replacement))
        assert old['xid']==new['xid'],('X server did not exercise actual ID reuse',old,new)
        assert old['generation']!=new['generation']
        keyboard.disconnect_injector(old);ping(replacement)
        results.append('actual-reused-resource-with-new-nonce-preserved')
        stop_process(replacement)
        for terminate_helper in (False,True):
            with tempfile.TemporaryDirectory(prefix='luda-disconnect-barrier-') as directory:
                base=Path(directory);original=client();old=json.loads(read(original))
                helper=subprocess.Popen([sys.executable,__file__,'--disconnect',json.dumps(old),directory],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                children.append(helper)
                until(lambda:(base/'entered').exists())
                stop_process(original)
                replacement=client()
                # Competing connection cannot allocate/reuse any XID while
                # nonce validation and XKillClient are one grabbed operation.
                assert not select.select([replacement.stdout],[],[],.15)[0]
                if terminate_helper:helper.kill()
                else:(base/'continue').write_text('finish owned disconnect')
                assert helper.wait(timeout=3)==(-9 if terminate_helper else 0)
                json.loads(read(replacement));ping(replacement)
                results.append('helper-death-releases-server-grab' if terminate_helper else 'competing-replacement-blocked-until-disconnect-finishes')
                stop_process(replacement)
    finally:
        for child in children:
            stop_process(child)
            if child.stdin:child.stdin.close()
            if child.stdout:child.stdout.close()
        keyboard.close()
    output=Path(__file__).resolve().parents[1]/'artifacts/injector-reuse';output.mkdir(parents=True,exist_ok=True)
    (output/'results.json').write_text(json.dumps({'passed':results,'count':len(results)},indent=2)+'\n')
    print(json.dumps({'passed':results,'count':len(results)}))

if __name__=='__main__':
    if len(sys.argv)>1:child_mode()
    else:main()
