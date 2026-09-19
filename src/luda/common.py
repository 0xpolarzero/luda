import contextvars
from contextlib import contextmanager
from dataclasses import dataclass
import os
import signal
import subprocess
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
    try:
        process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.PIPE, start_new_session=True)
    except FileNotFoundError as exc:
        raise DesktopError("DEPENDENCY_MISSING", f"Missing executable: {args[0]}") from exc
    mark_effect(effect)
    deadline = time.monotonic() + timeout
    first = True
    try:
        while True:
            if not cleanup:
                checkpoint()
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise DesktopError("TIMEOUT", "Command timed out. Inspect before retrying.", effect=effect)
            try:
                output, error = process.communicate(input=data if first else None, timeout=min(remaining, .05))
                break
            except subprocess.TimeoutExpired:
                first = False
        if process.returncode:
            raise DesktopError("BACKEND_ERROR", error.decode(errors="replace")[:600], effect=effect)
        return output
    except BaseException:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.communicate()
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
