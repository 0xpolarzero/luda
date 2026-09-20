import contextvars
from contextlib import contextmanager
from dataclasses import dataclass
import os
import re
import selectors
import signal
import subprocess
import tempfile
import threading
import time

from .timing import elapsed_time


class DesktopError(Exception):
    def __init__(self, code, message, *, effect="none", details=None):
        super().__init__(message)
        self.code, self.effect, self.details = code, effect, details or {}


@dataclass
class Operation:
    deadline: float
    cancelled: threading.Event
    effect: str = "none"
    guard: object = None


_current_operation = contextvars.ContextVar("luda_operation", default=None)


@contextmanager
def operation_scope(timeout=12, cancelled=None, guard=None):
    operation = Operation(elapsed_time() + timeout, cancelled or threading.Event(), guard=guard)
    token = _current_operation.set(operation)
    try:
        yield operation
    finally:
        _current_operation.reset(token)


def checkpoint():
    operation = _current_operation.get()
    if operation:
        if operation.cancelled.is_set():
            raise DesktopError("CANCELLED", "Operation cancelled. Inspect state before retrying.", effect=operation.effect)
        if elapsed_time() >= operation.deadline:
            raise DesktopError("TIMEOUT", "Overall operation deadline exceeded. Inspect state before retrying.", effect=operation.effect)
        if operation.guard:
            try:
                operation.guard()
            except DesktopError as exc:
                if operation.effect != 'none' and exc.effect == 'none':
                    exc.effect = 'uncertain'
                raise


def mark_effect(effect="uncertain"):
    operation = _current_operation.get()
    if operation and effect != "none":
        operation.effect = "uncertain"


def stop_process(process, timeout=1):
    """Bounded child cleanup; no signal to unrelated process groups."""
    if process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=timeout)


def run(args, *, data=None, timeout=3, effect="none", cleanup=False,
        max_output_bytes=16 * 1024 * 1024):
    """Run argv with bounded combined output, deadline and cancellation.

    Private seekable stdin avoids partial-write loss. Output is drained in fixed
    chunks; exceeding the bound kills the owned process group without returning
    captured data. Input-release cleanup may run after cancellation.
    """
    if type(max_output_bytes) is not int or max_output_bytes < 0:
        raise DesktopError("INVALID_ARGUMENT", "Output byte limit must be a nonnegative integer.")
    if not cleanup:
        checkpoint()
    source = tempfile.TemporaryFile() if data is not None else None
    try:
        if source:
            source.write(data)
            source.seek(0)
        process = subprocess.Popen(args, stdin=source if source else subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   start_new_session=True)
    except FileNotFoundError as exc:
        raise DesktopError("DEPENDENCY_MISSING", f"Missing executable: {args[0]}") from exc
    finally:
        if source:
            source.close()
    mark_effect(effect)
    deadline = elapsed_time() + timeout
    streams = selectors.DefaultSelector()
    output, error = bytearray(), bytearray()
    total = 0
    try:
        for pipe, buffer in ((process.stdout, output), (process.stderr, error)):
            os.set_blocking(pipe.fileno(), False)
            streams.register(pipe, selectors.EVENT_READ, buffer)
        while streams.get_map() or process.poll() is None:
            if not cleanup:
                checkpoint()
            remaining = deadline - elapsed_time()
            if remaining <= 0:
                raise DesktopError("TIMEOUT", "Command timed out. Inspect before retrying.", effect=effect)
            for key, _ in streams.select(timeout=min(remaining, .05)):
                try:
                    # Read at most one byte beyond the allowance to detect an
                    # overflow without allocating a large temporary payload.
                    chunk = os.read(key.fd, min(65536, max_output_bytes - total + 1))
                except BlockingIOError:
                    continue
                if not chunk:
                    streams.unregister(key.fileobj)
                    continue
                total += len(chunk)
                if total > max_output_bytes:
                    raise DesktopError("OUTPUT_LIMIT", "Backend output exceeded the configured byte limit; inspect state before retrying.",
                                       effect=effect, details={"limit_bytes": max_output_bytes})
                key.data.extend(chunk)
        if process.returncode:
            raise DesktopError("BACKEND_ERROR", error[:600].decode(errors="replace"), effect=effect)
        return bytes(output)
    except BaseException:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            # Do not let cleanup conceal the original error. The owned group
            # was signalled, and inherited pipes are closed below independently.
            pass
        raise
    finally:
        streams.close()
        process.stdout.close()
        process.stderr.close()


def process_identity(pid):
    from pathlib import Path
    try:
        # comm may contain spaces or parentheses. Fields after final ')' start at field 3.
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError) as e:
        raise DesktopError("STALE_TARGET", "Target process no longer exists.") from e


def validate_text(text):
    try:
        size = len(text.encode("utf-8"))
    except UnicodeEncodeError as exc:
        raise DesktopError("UNSUPPORTED_TEXT", "Unpaired Unicode surrogates cannot be encoded as UTF-8.") from exc
    if size > 1_000_000:
        raise DesktopError("TEXT_TOO_LARGE", "Text exceeds the 1 MB limit; no input was sent.")
    bad = [c for c in text if (ord(c) < 32 and c not in "\n\t") or ord(c) == 127]
    if bad:
        raise DesktopError("UNSUPPORTED_TEXT", "Control characters including CR, NUL and Escape are rejected; LF and Tab are allowed. No normalization is performed.")


def display_identity(display):
    """Equivalent local X display spellings share one input lock, across screens."""
    match = re.fullmatch(r'(.*?):(\d+)(?:\.\d+)?', display)
    if not match:
        return display
    host, number = match.groups()
    host = host.casefold()
    if host in ('', 'unix', 'unix/', 'localhost', '127.0.0.1', '[::1]'):
        host = 'local'
    return f'{host}:{int(number)}'
