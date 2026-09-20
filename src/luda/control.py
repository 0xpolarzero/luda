"""Cooperative per-display pause shared by CLI and every MCP server instance."""
from contextlib import contextmanager
import fcntl
import json
import math
import stat
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

    @staticmethod
    def _unavailable():
        return DesktopError('CONTROL_UNAVAILABLE', 'Desktop control state is unsafe or unavailable; check runtime file integrity, storage and descriptor limits before further input.')

    @staticmethod
    def _check_file(fd):
        value = os.fstat(fd)
        if (not stat.S_ISREG(value.st_mode) or value.st_uid != os.getuid()
                or stat.S_IMODE(value.st_mode) != 0o600 or value.st_nlink != 1
                or value.st_size > 4096):
            raise Control._unavailable()

    def status(self):
        fd = None
        try:
            try:
                fd = os.open(self.path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
            except FileNotFoundError:
                return {'paused':False,'revision':0}
            self._check_file(fd)
            raw = os.read(fd, 4097)
            if len(raw) > 4096:
                raise self._unavailable()
            data = json.loads(raw)
            if (not isinstance(data, dict) or set(data) - {'paused', 'revision', 'updated_at'}
                    or not isinstance(data.get('paused'), bool)
                    or type(data.get('revision')) is not int or not 0 <= data['revision'] < 2**63):
                raise self._unavailable()
            if 'updated_at' in data and (type(data['updated_at']) not in (int, float) or not math.isfinite(data['updated_at'])):
                raise self._unavailable()
            return data
        except (OSError, ValueError, RecursionError, OverflowError) as exc:
            raise self._unavailable() from exc
        finally:
            if fd is not None:
                os.close(fd)

    def require_active(self):
        if self.status()['paused']:
            raise DesktopError('CONTROL_PAUSED','Desktop input is paused. Observe freely; resume only when control is intended.')

    def set_paused(self, paused):
        if not isinstance(paused,bool):
            raise DesktopError('INVALID_ARGUMENT','paused must be boolean.')
        descriptor = None
        temporary = None
        try:
            descriptor = os.open(self.lock_path, os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW|os.O_NONBLOCK,0o600)
            self._check_file(descriptor)
            fcntl.flock(descriptor,fcntl.LOCK_EX|fcntl.LOCK_NB)
            previous = self.status()
            if previous['revision'] == 2**63 - 1:
                raise self._unavailable()
            state = {'paused':paused,'revision':previous['revision']+1,'updated_at':time.time()}
            with tempfile.NamedTemporaryFile(mode='w',dir=self.runtime,delete=False) as output:
                temporary = Path(output.name)
                json.dump(state,output)
                output.flush();os.fsync(output.fileno())
            temporary.replace(self.path)
            return state
        except BlockingIOError as exc:
            raise DesktopError('BUSY','Another controller is updating pause state; retry status.') from exc
        except OSError as exc:
            raise self._unavailable() from exc
        finally:
            if descriptor is not None:
                os.close(descriptor)
            if temporary:
                temporary.unlink(missing_ok=True)
