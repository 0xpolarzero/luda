"""Cooperative per-display pause shared by CLI and every MCP server instance."""
from contextlib import contextmanager
import fcntl
import json
import os
from pathlib import Path
import tempfile
import time

from .common import DesktopError


class Control:
    def __init__(self, runtime: Path, display_key: str):
        self.runtime = runtime
        self.path = runtime / f'{display_key}.control.json'
        self.lock_path = runtime / f'{display_key}.control.lock'

    def status(self):
        try:
            fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW)
        except FileNotFoundError:
            return {'paused':False,'revision':0}
        except OSError as exc:
            raise DesktopError('CONTROL_UNAVAILABLE','Cannot safely read desktop control state.') from exc
        with os.fdopen(fd) as source:
            try:
                data = json.load(source)
            except (ValueError,OSError) as exc:
                raise DesktopError('CONTROL_UNAVAILABLE','Control state is unreadable; refusing further input.') from exc
        if not isinstance(data,dict) or not isinstance(data.get('paused'),bool) or not isinstance(data.get('revision'),int):
            raise DesktopError('CONTROL_UNAVAILABLE','Invalid control state; refusing further input.')
        return data

    def require_active(self):
        if self.status()['paused']:
            raise DesktopError('CONTROL_PAUSED','Desktop input is paused. Observe freely; resume only when control is intended.')

    def set_paused(self, paused):
        if not isinstance(paused,bool):
            raise DesktopError('INVALID_ARGUMENT','paused must be boolean.')
        descriptor = os.open(self.lock_path, os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW,0o600)
        temporary = None
        try:
            fcntl.flock(descriptor,fcntl.LOCK_EX|fcntl.LOCK_NB)
            previous = self.status()
            state = {'paused':paused,'revision':previous['revision']+1,'updated_at':time.time()}
            with tempfile.NamedTemporaryFile(mode='w',dir=self.runtime,delete=False) as output:
                temporary = Path(output.name)
                json.dump(state,output)
                output.flush();os.fsync(output.fileno())
            temporary.replace(self.path)
            return state
        except BlockingIOError as exc:
            raise DesktopError('BUSY','Another controller is updating pause state; retry status.') from exc
        finally:
            os.close(descriptor)
            if temporary:
                temporary.unlink(missing_ok=True)
