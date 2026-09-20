"""Explicit same-account desktop session selection; never starts or replays apps."""
from contextlib import ExitStack, contextmanager
import os
from pathlib import Path

from .common import DesktopError, checkpoint, display_identity, environment_scope, process_identity, run

_SESSION_KEYS = ('DISPLAY', 'DBUS_SESSION_BUS_ADDRESS', 'XDG_RUNTIME_DIR', 'XAUTHORITY', 'XDG_SESSION_ID')


def _session(pid, uid):
    path = Path('/proc') / str(pid)
    try:
        if path.stat().st_uid != uid or not os.path.samefile(path/'exe', '/usr/bin/xfce4-session'):
            return None
        start = process_identity(pid)
        with (path/'environ').open('rb') as source:
            raw = source.read(1024 * 1024 + 1)
        if len(raw) > 1024 * 1024:
            return None
        env = dict(item.decode().split('=', 1) for item in raw.split(b'\0') if b'=' in item)
        if not env.get('DISPLAY') or not env.get('DBUS_SESSION_BUS_ADDRESS'):
            return None
        if process_identity(pid) != start:
            return None
        return {'pid':pid, 'start':start, 'environment':env}
    except (OSError, UnicodeError, DesktopError):
        return None


def select_session(session_pid=None):
    if session_pid is not None and (type(session_pid) is not int or session_pid <= 0):
        raise DesktopError('INVALID_ARGUMENT', 'session_pid must be a positive integer or omitted.')
    candidates = [session_pid] if session_pid is not None else [int(p.name) for p in Path('/proc').iterdir() if p.name.isdigit()]
    matches = []
    for pid in candidates:
        checkpoint()
        match = _session(pid, os.getuid())
        if match:
            matches.append(match)
    if len(matches) != 1:
        raise DesktopError('SESSION_NOT_FOUND' if not matches else 'SESSION_AMBIGUOUS',
                           'Select one running XFCE session owned by this account using session_pid.',
                           details={'candidate_count':len(matches), 'session_pids':[item['pid'] for item in matches]})
    return matches[0]


def _unchanged(selected):
    current = _session(selected['pid'], os.getuid())
    if current is None or current['start'] != selected['start'] or any(
            current['environment'].get(k) != selected['environment'].get(k) for k in _SESSION_KEYS):
        raise DesktopError('SESSION_CHANGED', 'Selected session changed during validation; existing backend preserved.')


def prepare_reconnect(old, session_pid, factory):
    """Prepare under both peer locks. Caller must hold its nonblocking operation gate.

    The returned context keeps peer locks held through the caller's atomic swap.
    The old backend is closed by the caller only after its transaction exits.
    """
    return _prepared(old, session_pid, factory)


@contextmanager
def _prepared(old, session_pid, factory):
    selected = select_session(session_pid)
    env = dict(old.environment)
    for key in _SESSION_KEYS:
        env.pop(key, None)
        if key in selected['environment']:
            env[key] = selected['environment'][key]
    if 'XAUTHORITY' not in env:
        authority = Path(env.get('HOME', str(Path.home()))) / '.Xauthority'
        if authority.is_file():
            env['XAUTHORITY'] = str(authority)
    candidate = factory(environment=env)
    accepted = False
    try:
        with ExitStack() as stack:
            stack.enter_context(old.transaction())
            if display_identity(env['DISPLAY']) != display_identity(old.environment.get('DISPLAY', '')):
                stack.enter_context(candidate.transaction())
            stack.enter_context(environment_scope(env))
            _unchanged(selected)
            geometry = candidate.display().geometry(candidate.display().root)
            # An existing session bus must answer; this never auto-launches a bus.
            run(['dbus-send', '--session', '--print-reply', '--reply-timeout=1500',
                 '--dest=org.freedesktop.DBus', '/org/freedesktop/DBus',
                 'org.freedesktop.DBus.GetId'], timeout=2, max_output_bytes=4096)
            _unchanged(selected)
            checkpoint()
            result = {'effect':'verified', 'session_pid':selected['pid'], 'session_start':selected['start'],
                      'display':env['DISPLAY'], 'geometry':geometry, 'session_bus_available':True,
                      'observations_invalidated':True, 'control':candidate.control.status(),
                      'next_step':'Observe windows again. Run desktop_doctor for accessibility and lock-state capabilities.'}
            yield candidate, result
            accepted = True
    finally:
        if not accepted:
            candidate.close()
