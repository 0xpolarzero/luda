import contextvars
from contextlib import contextmanager
from dataclasses import dataclass
import os
import re
import signal
import subprocess
import tempfile
import threading
import time


class DesktopError(Exception):
    def __init__(self, code, message, *, effect="none", details=None):
        super().__init__(message)
        self.code, self.effect, self.details = code, effect, details or {}


@dataclass
class Operation:
    deadline: float
    cancelled: threading.Event
    effect: str = "none"


_current_operation = contextvars.ContextVar("luda_operation", default=None)


@contextmanager
def operation_scope(timeout=12, cancelled=None):
    operation = Operation(time.monotonic() + timeout, cancelled or threading.Event())
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
        if time.monotonic() >= operation.deadline:
            raise DesktopError("TIMEOUT", "Overall operation deadline exceeded. Inspect state before retrying.", effect=operation.effect)


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


def run(args, *, data=None, timeout=3, effect="none", cleanup=False):
    """No shell; honor both command and overall deadlines and cancellation.

    Input-release cleanup is allowed after cancellation, with its own short timeout.
    """
    if not cleanup:
        checkpoint()
    # A seekable private input file lets communicate() be polled without losing
    # partially written stdin after TimeoutExpired (CPython only resumes reads).
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
    deadline = time.monotonic() + timeout
    try:
        while True:
            if not cleanup:
                checkpoint()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise DesktopError("TIMEOUT", "Command timed out. Inspect before retrying.", effect=effect)
            try:
                output, error = process.communicate(timeout=min(remaining, .05))
                break
            except subprocess.TimeoutExpired:
                continue
        if process.returncode:
            raise DesktopError("BACKEND_ERROR", error.decode(errors="replace")[:600], effect=effect)
        return output
    except BaseException:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        try:
            process.communicate(timeout=1)
        except subprocess.TimeoutExpired:
            # A descendant could have detached while retaining stdout. Do not
            # let an inherited pipe defeat the overall cancellation bound.
            process.stdout.close()
            process.stderr.close()
            process.wait(timeout=1)
        raise


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
