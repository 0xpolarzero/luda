"""Best-effort visible agent pointer, isolated from input and the tool process."""
import os
import select
import subprocess
import sys
import threading


class Cursor:
    def __init__(self, environment=None):
        self._environment = dict(os.environ if environment is None else environment)
        self._process = None
        self.window_id = None
        self._lock = threading.RLock()

    @property
    def available(self):
        """Whether a renderer is currently running (startup is lazy)."""
        return self._process is not None and self._process.poll() is None and self.window_id is not None

    def _start(self):
        if self._process is not None:
            if self._process.poll() is None:
                return True
            self.close()
        try:
            self._process = subprocess.Popen(
                [sys.executable, '-m', 'luda._cursor_overlay'],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                env=self._environment)
            if not select.select([self._process.stdout], [], [], .5)[0]:
                raise TimeoutError()
            raw = os.read(self._process.stdout.fileno(), 64)
            self.window_id = int(raw.strip())
            if not 0 < self.window_id <= 0xffffffff:
                raise ValueError()
            os.set_blocking(self._process.stdin.fileno(), False)
            return True
        except (OSError, ValueError, TimeoutError):
            self.close()
            return False

    def show(self, x, y, kind='move'):
        """Show the action target without moving the desktop's real pointer."""
        with self._lock:
            if any(isinstance(v, bool) or not isinstance(v, int) or not -32768 <= v <= 32767 for v in (x, y)):
                return
            if self._start():
                self._send(f'{x} {y} {int(kind != "move")}\n'.encode())

    def _send(self, data):
        try:
            os.write(self._process.stdin.fileno(), data)
        except BlockingIOError:
            pass  # Visual feedback must never delay actual input.
        except (OSError, ValueError):
            self.close()

    def hide(self):
        with self._lock:
            if self._process is not None:
                self._send(b'hide\n')
                if self._process is not None:
                    try:
                        if not select.select([self._process.stdout], [], [], .2)[0]:
                            raise TimeoutError()
                        if os.read(self._process.stdout.fileno(), 64) != b'hidden\n':
                            raise ValueError()
                    except (OSError, ValueError, TimeoutError):
                        self.close()

    def close(self):
        with self._lock:
            process, self._process = self._process, None
            self.window_id = None
            if process is None:
                return
            for stream in (process.stdin, process.stdout):
                if stream:
                    stream.close()
            try:
                process.wait(timeout=.2)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=.2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=.2)
