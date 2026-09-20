"""Bounded cooperative FIFO admission; queued tickets never contain operations."""
import fcntl
import json
import math
import os
from pathlib import Path
import re
import stat
import uuid

from .common import DesktopError, checkpoint, process_identity
from .timing import elapsed_time

LEASE_SECONDS = 2.0
MAX_CLIENTS = 64
MAX_BYTES = 32768
RETRY_MS = 100


class Admission:
    def __init__(self, runtime: Path, display_key: str):
        if not re.fullmatch(r'[a-zA-Z0-9_-]{1,64}', display_key):
            raise DesktopError('INVALID_ARGUMENT', 'Invalid display admission key.')
        self.runtime = Path(runtime)
        self.lock_name = display_key + '.admission.lock'
        self.state_name = display_key + '.admission.json'
        self.nonce = uuid.uuid4().hex
        self.pid = os.getpid()
        self.start = process_identity(self.pid)
        self.boot = Path('/proc/sys/kernel/random/boot_id').read_text().strip()

    @staticmethod
    def _unsafe():
        return DesktopError('ADMISSION_UNAVAILABLE', 'Display admission state is unsafe or unreadable; no operation started.')

    @staticmethod
    def _check_file(fd):
        value = os.fstat(fd)
        if not stat.S_ISREG(value.st_mode) or value.st_uid != os.getuid() or stat.S_IMODE(value.st_mode) != 0o600 or value.st_nlink != 1:
            raise Admission._unsafe()

    def _open(self):
        directory = lock = None
        try:
            directory = os.open(self.runtime, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
            value = os.fstat(directory)
            if value.st_uid != os.getuid() or value.st_mode & 0o077:
                raise self._unsafe()
            lock = os.open(self.lock_name, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600, dir_fd=directory)
            self._check_file(lock)
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise self._busy(None, 'Another client is updating admission.') from exc
            return directory, lock
        except BaseException:
            if lock is not None:os.close(lock)
            if directory is not None:os.close(directory)
            raise

    def _read(self, directory):
        try:
            fd = os.open(self.state_name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
        except FileNotFoundError:
            return []
        try:
            self._check_file(fd)
            with os.fdopen(fd, 'rb', closefd=False) as stream:
                raw = stream.read(MAX_BYTES + 1)
            if len(raw) > MAX_BYTES:
                raise self._unsafe()
            data = json.loads(raw)
            if not isinstance(data, dict) or set(data) != {'version', 'boot', 'queue'} or data['version'] != 1:
                raise self._unsafe()
            if not isinstance(data['boot'], str) or not re.fullmatch(r'[a-f0-9-]{36}', data['boot']):
                raise self._unsafe()
            queue = data['queue']
            if not isinstance(queue, list) or len(queue) > MAX_CLIENTS:
                raise self._unsafe()
            seen = set()
            for item in queue:
                if not isinstance(item, dict) or set(item) != {'nonce', 'pid', 'start', 'expires'}:
                    raise self._unsafe()
                if not isinstance(item['nonce'], str) or not re.fullmatch(r'[a-f0-9]{32}', item['nonce']) or item['nonce'] in seen:
                    raise self._unsafe()
                seen.add(item['nonce'])
                if type(item['pid']) is not int or item['pid'] <= 0 or not isinstance(item['start'], str) or not re.fullmatch(r'[0-9]{1,32}', item['start']):
                    raise self._unsafe()
                if type(item['expires']) not in (int, float) or not math.isfinite(item['expires']) or item['expires'] < 0:
                    raise self._unsafe()
            return queue if data['boot'] == self.boot else []
        except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
            raise self._unsafe() from exc
        finally:
            os.close(fd)

    def _write(self, directory, queue):
        encoded = json.dumps({'version':1, 'boot':self.boot, 'queue':queue}, separators=(',', ':')).encode()
        if len(encoded) > MAX_BYTES:
            raise self._unsafe()
        # One fixed pending name bounds crash orphans to one file per display.
        # The arbitration lock proves no cooperating writer is still using it.
        name = self.state_name + '.pending'
        fd = None
        try:
            try:
                pending = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=directory)
            except FileNotFoundError:
                pass
            else:
                try:self._check_file(pending)
                finally:os.close(pending)
                os.unlink(name, dir_fd=directory)
            fd = os.open(name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
            with os.fdopen(fd, 'wb', closefd=False) as stream:
                stream.write(encoded)
            os.replace(name, self.state_name, src_dir_fd=directory, dst_dir_fd=directory)
        finally:
            if fd is not None:os.close(fd)
            if fd is not None:
                try:os.unlink(name, dir_fd=directory)
                except FileNotFoundError:pass

    def _live(self, ticket, now):
        if ticket['expires'] <= now or ticket['expires'] > now + LEASE_SECONDS + .1:
            return False
        try:
            return Path('/proc', str(ticket['pid'])).stat().st_uid == os.getuid() and process_identity(ticket['pid']) == ticket['start']
        except (OSError, DesktopError):
            return False

    def _busy(self, position, message='Another client has priority for this display.'):
        return DesktopError('BUSY', message + ' No operation started; retry explicitly after the suggested delay.',
                            details={'queued':position is not None, 'queue_position':position,
                                     'retry_after_ms':RETRY_MS, 'priority_lease_ms':int(LEASE_SECONDS * 1000) if position is not None else 0})

    def acquire(self, display_fd):
        """Take the existing display flock or return BUSY; never waits/replays."""
        try:
            checkpoint()
        except DesktopError:
            self.cancel()
            raise
        if os.getpid() != self.pid:
            raise self._unsafe()
        directory = lock = None
        acquired = False
        complete = False
        queue = None
        try:
            self._check_file(display_fd)
            directory, lock = self._open()
            now = elapsed_time()
            queue = [ticket for ticket in self._read(directory) if self._live(ticket, now)]
            ticket = next((item for item in queue if item['nonce'] == self.nonce), None)
            if ticket is None:
                if len(queue) >= MAX_CLIENTS:
                    self._write(directory, queue)
                    raise self._busy(None, 'The bounded admission queue is full.')
                ticket = {'nonce':self.nonce, 'pid':self.pid, 'start':self.start, 'expires':now + LEASE_SECONDS}
                queue.append(ticket)
            else:
                ticket['expires'] = now + LEASE_SECONDS
            checkpoint()
            if queue[0]['nonce'] != self.nonce:
                self._write(directory, queue)
                raise self._busy(queue.index(ticket) + 1)
            try:
                fcntl.flock(display_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                self._write(directory, queue)
                raise self._busy(1, 'Another operation currently holds this display.') from exc
            acquired = True
            checkpoint()
            self._write(directory, queue[1:])
            complete = True
        except DesktopError as exc:
            if exc.code in ('CANCELLED', 'TIMEOUT', 'CONTROL_PAUSED') and directory is not None and queue is not None:
                try:self._write(directory, [item for item in queue if item['nonce'] != self.nonce])
                except (OSError, DesktopError):pass
            raise
        except OSError as exc:
            raise self._unsafe() from exc
        finally:
            if acquired and not complete:
                fcntl.flock(display_fd, fcntl.LOCK_UN)
            if lock is not None:os.close(lock)
            if directory is not None:os.close(directory)

    @staticmethod
    def release(display_fd):
        fcntl.flock(display_fd, fcntl.LOCK_UN)

    def cancel(self):
        """Best-effort removal of an idle ticket; a busy registry expires it."""
        directory = lock = None
        try:
            directory, lock = self._open()
            now = elapsed_time()
            queue = [ticket for ticket in self._read(directory) if ticket['nonce'] != self.nonce and self._live(ticket, now)]
            self._write(directory, queue)
            return True
        except (DesktopError, OSError):
            return False
        finally:
            if lock is not None:os.close(lock)
            if directory is not None:os.close(directory)
