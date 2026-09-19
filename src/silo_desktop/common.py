import subprocess


class DesktopError(Exception):
    def __init__(self, code, message, *, effect="none", details=None):
        super().__init__(message)
        self.code, self.effect, self.details = code, effect, details or {}


def run(args, *, data=None, timeout=3, effect="none"):
    """Never invoke a shell. A timeout after input is an uncertain outcome."""
    try:
        p = subprocess.run(args, input=data, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise DesktopError("TIMEOUT", "Operation timed out; inspect before retrying.", effect=effect) from e
    except FileNotFoundError as e:
        raise DesktopError("DEPENDENCY_MISSING", f"Missing executable: {args[0]}") from e
    if p.returncode:
        raise DesktopError("BACKEND_ERROR", p.stderr.decode(errors="replace")[:600], effect=effect)
    return p.stdout


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
