"""Disposable-process kernel resource limits; never changes the caller limits."""
import json
import os
from pathlib import Path
import resource
import sys
import tempfile
import time

from luda.common import run
from luda.desktop import Desktop


def child_pids():
    values=set()
    for task in Path('/proc/self/task').iterdir():
        values.update((task/'children').read_text().split())
    return sorted(values)


def probe(mode):
    kind=resource.RLIMIT_AS if mode.startswith('memory') else resource.RLIMIT_NOFILE
    prior=resource.getrlimit(kind)
    descriptors=[]
    baseline_fds=len(list(Path('/proc/self/fd').iterdir()))
    with tempfile.TemporaryDirectory(prefix='luda-private-resource-') as folder:
        sentinel=Path(folder)/'late-effect'
        # If capture cleanup fails, this owned child would write an independent
        # marker after its output has been consumed. No X11 input is generated.
        code='import os,time,pathlib,sys\nfor i in range(512):os.write(1,b"x"*65536)\ntime.sleep(.5);pathlib.Path(sys.argv[1]).write_text("late")'
        began=time.monotonic()
        try:
            if kind==resource.RLIMIT_NOFILE:
                resource.setrlimit(kind,(min(48,prior[0]),prior[1]))
                while True:
                    try:descriptors.append(os.open('/dev/null',os.O_RDONLY))
                    except OSError:break
            else:
                size=int(next(x.split()[1] for x in Path('/proc/self/status').read_text().splitlines() if x.startswith('VmSize:')))*1024
                resource.setrlimit(kind,(size+8*1024*1024,prior[1]))
            try:
                if mode=='startup-fd':
                    desktop=Desktop();desktop.close()
                else:
                    run([sys.executable,'-c',code,str(sentinel)],
                        data=b'owned synthetic stdin' if mode=='stdin-fd' else None,
                        effect='uncertain' if mode=='memory-after-dispatch' else 'none',
                        max_output_bytes=64*1024*1024)
            except BaseException as exc:
                error={'type':type(exc).__name__,'code':getattr(exc,'code',None),'effect':getattr(exc,'effect',None)}
            else:
                error={'type':None}
            elapsed=time.monotonic()-began
        finally:
            for fd in descriptors:os.close(fd)
            resource.setrlimit(kind,prior)
        # A fully restored limit and actual next subprocess establish recovery.
        recovery=run(['/bin/echo','recovered']).decode().strip()
        time.sleep(.7)
        return {'mode':mode,'error':error,'elapsed_seconds':elapsed,
                'late_effect':sentinel.exists(),'recovery':recovery,
                'remaining_children':child_pids(),
                'fd_delta':len(list(Path('/proc/self/fd').iterdir()))-baseline_fds,
                'limit_restored':resource.getrlimit(kind)==prior}

if __name__=='__main__':
    print(json.dumps(probe(sys.argv[1])))
