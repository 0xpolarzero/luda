"""Explicit root-to-desktop launcher; no guessed display or arbitrary shell."""
import argparse
import os
import math
import time
from .timing import elapsed_time
from pathlib import Path
import pwd
import sys


class SessionDiscoveryError(SystemExit):
    def __init__(self, count):
        self.count = count
        super().__init__(f'Expected one ready XFCE session for this account, found {count}. Start its desktop or specify --session-pid; DISPLAY and session D-Bus must be available.')


def discover(uid, session_pid=None):
    matches = []
    for path in Path('/proc').iterdir():
        if not path.name.isdigit() or (session_pid and int(path.name) != session_pid):
            continue
        try:
            if path.stat().st_uid != uid or (path/'comm').read_text().strip() != 'xfce4-session':
                continue
            env = dict(item.decode().split('=', 1) for item in (path/'environ').read_bytes().split(b'\0') if b'=' in item)
            if env.get('DISPLAY') and env.get('DBUS_SESSION_BUS_ADDRESS'):
                matches.append(env)
        except (OSError, UnicodeError):
            continue
    if len(matches) != 1:
        raise SessionDiscoveryError(len(matches))
    return matches[0]


def wait_for_session(uid, session_pid=None, timeout=5):
    deadline = elapsed_time() + timeout
    while True:
        try:
            return discover(uid, session_pid)
        except SessionDiscoveryError as exc:
            if exc.count != 0 or elapsed_time() >= deadline:
                raise
            time.sleep(min(.1,max(0,deadline-elapsed_time())))


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--user', default='silo-desktop')
    p.add_argument('--session-pid', type=int)
    p.add_argument('--cwd', help='Absolute working directory for the command; default is the desktop account home, or / if unavailable.')
    p.add_argument('--wait', type=float, default=5, help='Wait up to this many seconds for the selected session (0–30; default 5).')
    p.add_argument('command', nargs=argparse.REMAINDER)
    args = p.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command:
        p.error('Supply an executable after --')
    if args.cwd is not None and not os.path.isabs(args.cwd):
        p.error('--cwd must be an absolute path')
    # Resolve a relative executable before moving away from the SSH caller's cwd.
    if '/' in command[0] and not os.path.isabs(command[0]):
        command[0] = os.path.abspath(command[0])
    if not math.isfinite(args.wait) or not 0 <= args.wait <= 30:
        p.error('--wait must be 0–30 seconds')
    if args.session_pid is not None and args.session_pid<=0:
        p.error('--session-pid must be positive')
    try:
        account = pwd.getpwnam(args.user)
    except KeyError:
        p.error('The selected desktop account does not exist')
    if os.getuid() not in (0, account.pw_uid):
        raise SystemExit('Run as the desktop account or root; no automatic privilege escalation.')
    session = wait_for_session(account.pw_uid, args.session_pid, args.wait)
    env = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': account.pw_dir,
           'USER': account.pw_name, 'LOGNAME': account.pw_name, 'LANG': 'C.UTF-8',
           'PYTHONUNBUFFERED': '1', 'NO_AT_BRIDGE': '0'}
    for key in ('DISPLAY', 'DBUS_SESSION_BUS_ADDRESS', 'XDG_RUNTIME_DIR', 'XAUTHORITY', 'XDG_SESSION_ID'):
        if key in session:
            env[key] = session[key]
    env.setdefault('XAUTHORITY', str(Path(account.pw_dir)/'.Xauthority'))
    if not Path(env['XAUTHORITY']).is_file():
        raise SystemExit('Desktop Xauthority is missing.')
    if os.getuid() == 0:
        os.initgroups(account.pw_name, account.pw_gid)
        os.setgid(account.pw_gid)
        os.setuid(account.pw_uid)
    # An SSH root session often starts in /root, which becomes inaccessible
    # after setuid. Libraries may inspect cwd before serving even one request.
    # Check access as the selected account, never as the privileged caller.
    try:
        os.chdir(args.cwd if args.cwd is not None else account.pw_dir)
    except OSError:
        if args.cwd is not None:
            raise SystemExit('The selected working directory is inaccessible to the desktop account.') from None
        os.chdir('/')
    from .managed_browser import selected
    try:
        browser = selected(sys.prefix)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    if browser:
        env['LUDA_CHROMIUM_EXECUTABLE'] = browser['executable']
        env['LUDA_MANAGED_BROWSER_VERSION'] = browser['version']
        env['LUDA_MANAGED_BROWSER_SHA256'] = browser['sha256']
    os.execvpe(command[0], command, env)


if __name__ == '__main__':
    main()
