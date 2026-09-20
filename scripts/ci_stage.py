#!/usr/bin/env python3
"""Linux CI-only stage owner: bounded cleanup of this supervisor's descendants."""
import argparse
import ctypes
import json
import os
from pathlib import Path
import signal
import subprocess
import time


def processes():
    rows={}
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():continue
        try:
            fields=(path/'stat').read_text().rsplit(')',1)[1].split()
            rows[int(path.name)]=(int(fields[1]),fields[19],fields[0])
        except (OSError,ValueError,IndexError):pass
    return rows


def descendants(owner, rows):
    found={};parents={owner}
    while True:
        new={pid for pid,row in rows.items() if row[0] in parents and pid not in found}
        if not new:return found
        found.update({pid:rows[pid][1] for pid in new});parents=new


def send(pid,start,signum):
    # A pidfd prevents PID reuse between the final identity check and signal.
    try:
        fd=os.pidfd_open(pid)
        try:
            fields=Path('/proc',str(pid),'stat').read_text().rsplit(')',1)[1].split()
            if fields[19]==start:signal.pidfd_send_signal(fd,signum)
        finally:os.close(fd)
    except (ProcessLookupError,FileNotFoundError):pass


def run(argv, timeout, evidence):
    if ctypes.CDLL(None).prctl(36,1,0,0,0)!=0:raise RuntimeError('CI stage requires Linux subreaper support')
    parent=os.getppid();child=subprocess.Popen(argv,start_new_session=True)
    reason='completed';seen={};code=None
    try:
        deadline=time.monotonic()+timeout
        while True:
            seen.update(descendants(os.getpid(),processes()))
            code=child.poll()
            if code is not None:break
            if os.getppid()!=parent:reason='owner_lost';break
            if time.monotonic()>=deadline:reason='timeout';break
            time.sleep(.02)
    finally:
        # Even successful parents may leave detached writers. Adoption by this
        # isolated subreaper, not shared UID or executable name, defines ownership.
        started=time.monotonic();survivors={};empty=0
        while True:
            rows=processes();owned=descendants(os.getpid(),rows);seen.update(owned)
            for pid,start in owned.items():
                if rows[pid][0]==os.getpid() and pid!=child.pid:
                    try:os.waitpid(pid,os.WNOHANG)
                    except ChildProcessError:pass
                if rows[pid][2]!='Z':
                    send(pid,start,signal.SIGCONT)
                    send(pid,start,signal.SIGTERM if time.monotonic()-started<1 else signal.SIGKILL)
            child.poll()
            rows=processes();survivors={pid:start for pid,start in descendants(os.getpid(),rows).items() if rows[pid][2]!='Z'}
            # Reap remaining adopted zombies, including ones found after parent exit.
            for pid,row in rows.items():
                if row[0]==os.getpid() and pid!=child.pid and row[2]=='Z':
                    try:os.waitpid(pid,os.WNOHANG)
                    except ChildProcessError:pass
            empty=empty+1 if not survivors else 0
            if empty>=2 or time.monotonic()-started>=5:break
            time.sleep(.02)
        value={'reason':reason,'exit_code':code,'cleanup_confirmed':not survivors,
               'owned_processes_seen':len(seen),'survivors':list(survivors),'cleanup_seconds':round(time.monotonic()-started,3)}
        evidence.write_text(json.dumps(value,indent=2)+'\n')
    return 0 if reason=='completed' and code==0 and not survivors else 1


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--timeout',type=float,required=True)
    parser.add_argument('--evidence',type=Path,required=True)
    parser.add_argument('command',nargs=argparse.REMAINDER)
    args=parser.parse_args();command=args.command[1:] if args.command[:1]==['--'] else args.command
    if not command or not 0<args.timeout<=3600:parser.error('Require a command and timeout in (0,3600]')
    raise SystemExit(run(command,args.timeout,args.evidence))

if __name__=='__main__':main()
