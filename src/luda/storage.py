"""Redacted, actionable local storage/resource failures at desktop boundaries."""
from contextlib import contextmanager
import errno
import tempfile

from .common import DesktopError

_STORAGE = {errno.ENOSPC, errno.EDQUOT, errno.EROFS, errno.EACCES, errno.EPERM,
            errno.EIO, errno.ENOENT, errno.ENOTDIR}
_RESOURCES = {errno.EMFILE, errno.ENFILE, errno.ENOMEM, errno.EAGAIN}


@contextmanager
def storage_errors(operation, effect='none'):
    try:
        yield
    except OSError as exc:
        if exc.errno in _STORAGE:
            code = 'STORAGE_UNAVAILABLE'
            message = f'Cannot {operation}: check temporary storage space, quota, permissions and filesystem availability.'
        elif exc.errno in _RESOURCES:
            code = 'RESOURCE_UNAVAILABLE'
            message = f'Cannot {operation}: release file descriptors/process resources or increase the account limit.'
        else:
            # Unknown provider errors must not be mislabeled as a full disk.
            raise
        raise DesktopError(code, message, effect=effect,
                           details={'errno': errno.errorcode.get(exc.errno, 'UNKNOWN')}) from exc


@contextmanager
def staged_payload(directory, payload):
    """Flush fully before publishing; unlink even if buffered close raises."""
    source = tempfile.NamedTemporaryFile(dir=directory)
    try:
        source.write(payload)
        source.flush()
        yield source.name
    finally:
        # NamedTemporaryFile.__exit__ can skip cleanup after a failed flush;
        # its explicit close path performs unlink in a finally block.
        source.close()
