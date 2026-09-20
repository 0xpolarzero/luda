"""Private inherited-FD watchdog, no listening socket or user text."""
import os
import selectors
import subprocess
import sys
from .timing import elapsed_time


def main():
    descriptor=int(sys.argv[1]);button=sys.argv[2]
    if button not in ('1','2','3'):return 2
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
            subprocess.run(['xdotool','mouseup',button],stdin=subprocess.DEVNULL,
                           stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=2)
        except (OSError,subprocess.TimeoutExpired):return 1
    return 0

if __name__=='__main__':sys.exit(main())
