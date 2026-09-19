"""Explicit root-to-desktop launcher; no guessed display or arbitrary shell."""
import argparse
import os
from pathlib import Path
import pwd
import sys


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
        raise SystemExit(f'Expected one XFCE session for this account, found {len(matches)}. Specify --session-pid if needed.')
    return matches[0]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--user', default='silo-desktop')
    p.add_argument('--session-pid', type=int)
    p.add_argument('command', nargs=argparse.REMAINDER)
    args = p.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not command:
        p.error('Supply an executable after --')
    account = pwd.getpwnam(args.user)
    if os.getuid() not in (0, account.pw_uid):
        raise SystemExit('Run as the desktop account or root; no automatic privilege escalation.')
    session = discover(account.pw_uid, args.session_pid)
    env = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'HOME': account.pw_dir,
           'USER': account.pw_name, 'LOGNAME': account.pw_name, 'LANG': 'C.UTF-8',
           'PYTHONUNBUFFERED': '1', 'NO_AT_BRIDGE': '0'}
    for key in ('DISPLAY', 'DBUS_SESSION_BUS_ADDRESS', 'XDG_RUNTIME_DIR', 'XAUTHORITY'):
        if key in session:
            env[key] = session[key]
    env.setdefault('XAUTHORITY', str(Path(account.pw_dir)/'.Xauthority'))
    if not Path(env['XAUTHORITY']).is_file():
        raise SystemExit('Desktop Xauthority is missing.')
    if os.getuid() == 0:
        os.initgroups(account.pw_name, account.pw_gid)
        os.setgid(account.pw_gid)
        os.setuid(account.pw_uid)
    os.execvpe(command[0], command, env)


if __name__ == '__main__':
    main()
