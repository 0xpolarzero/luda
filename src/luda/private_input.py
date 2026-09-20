"""Session-owned independent input; helpers receive an opaque private identity."""
import json
import os
import select
import subprocess
import sys
import threading

from .common import DesktopError
from ._private_input import TOKEN_ENV, ROUTE_ENV, decode_token


class PrivateInput:
    def __init__(self, environment=None):
        self._environment = dict(os.environ if environment is None else environment)
        self._environment.pop(TOKEN_ENV, None)
        self._environment.pop(ROUTE_ENV, None)
        self._process = None
        self._token = None
        self._lock = threading.RLock()

    def environment(self):
        with self._lock:
            if self._process is not None and self._process.poll() is not None:
                self.close()
                raise DesktopError('INPUT_UNAVAILABLE', 'Private input owner exited; retry with a fresh observation.')
            if self._process is None:
                try:
                    self._process = subprocess.Popen([sys.executable, '-m', 'luda._private_input'],
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                        env=self._environment, start_new_session=True)
                    if not select.select([self._process.stdout], [], [], 2)[0]:
                        raise TimeoutError()
                    self._token = decode_token(os.read(self._process.stdout.fileno(), 2048))
                except (OSError, ValueError, TimeoutError, DesktopError):
                    self.close()
                    raise DesktopError('INPUT_UNAVAILABLE', 'Private input could not start; no shared input fallback.') from None
            return {**self._environment, ROUTE_ENV: 'private', TOKEN_ENV: json.dumps(self._token, separators=(',', ':'))}

    def close(self):
        with self._lock:
            process, self._process = self._process, None
            self._token = None
            if process is None:
                return
            if process.stdin:
                process.stdin.close()
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                process.kill()  # The owner watchdog removes the private pair.
                process.wait(timeout=2)
            if process.stdout:
                process.stdout.close()
