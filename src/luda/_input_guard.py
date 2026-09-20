"""Private inherited-FD watchdog, no listening socket or user text."""
import os
import json
import re
import selectors
import subprocess
import sys
from .timing import elapsed_time


def main():
    descriptor=int(sys.argv[1]);button=sys.argv[2];generation=sys.argv[3]
    if button not in ('1','2','3') or not re.fullmatch('[a-f0-9]{32}',generation):return 1
    with selectors.DefaultSelector() as watch:
        watch.register(descriptor,selectors.EVENT_READ)
        os.write(sys.stdout.fileno(),b'R')
        deadline=elapsed_time()+20
        armed=False;disarmed=False
        while elapsed_time()<deadline:
            if not watch.select(min(.1,max(0,deadline-elapsed_time()))):continue
            command=os.read(descriptor,1)
            if command==b'A':armed=True
            elif command==b'D':disarmed=True;break
            elif not command:break
    os.close(descriptor)
    if armed and not disarmed:
        # A parent crash closes the pipe. No parent process or inherited MCP
        # stream is needed to release the input in the original display session.
        try:
            result=subprocess.run([sys.executable,'-m','luda._input_native'],input=json.dumps({'operation':'release','button':button,'server_generation':generation}).encode()+b'\n',
                                  stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,timeout=2)
            proof=json.loads(result.stdout) if result.returncode==0 else {}
            if proof.get('session_changed') and proof.get('cleanup_skipped'):return 2
            if not proof.get('released'):return 1
        except (OSError,ValueError,subprocess.TimeoutExpired):return 1
    return 0

if __name__=='__main__':sys.exit(main())
