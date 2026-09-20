"""Private Linux browser owner: bounded IPC, EOF cleanup and descendant reaping."""
import ctypes
import json
import os
from pathlib import Path
import selectors
import shutil
import signal
import subprocess
import sys
import tempfile
import stat
import time

MAX_PACKET = 1024 * 1024


def identities():
    found = {}
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            tail = (entry / 'stat').read_text().rsplit(')', 1)[1].split()
            found[int(entry.name)] = (int(tail[1]), tail[19])
        except (OSError, ValueError, IndexError):
            continue
    return found


def descendants():
    table = identities()
    owned = {os.getpid()}
    while True:
        extra = {pid for pid, (parent, _) in table.items() if parent in owned}
        if extra <= owned:
            break
        owned.update(extra)
    return [(pid, table[pid][1]) for pid in owned if pid != os.getpid()]


def stop_owned():
    # Subreaper adoption retains ownership when Node/Chromium detach or exit.
    # PID descriptors plus a start-time recheck prevent recycled-PID signals.
    deadline = time.monotonic() + 2
    while time.monotonic() < deadline:
        children = descendants()
        if not children:
            return True
        for pid, start in children:
            fd = None
            try:
                fd = os.pidfd_open(pid)
                if identities().get(pid, (None, None))[1] == start:
                    signal.pidfd_send_signal(fd, signal.SIGKILL)
            except (ProcessLookupError, PermissionError, OSError):
                pass
            finally:
                if fd is not None:
                    os.close(fd)
        while True:
            try:
                if os.waitpid(-1, os.WNOHANG)[0] == 0:
                    break
            except ChildProcessError:
                break
        time.sleep(.02)
    return not descendants()


def clear_profile(directory, descriptor, identity):
    """Clear only the opened original root, never a replacement path's contents."""
    try:
        if (os.fstat(descriptor).st_dev, os.fstat(descriptor).st_ino) != identity:
            return False
        for entry in os.listdir(descriptor):
            info = os.stat(entry, dir_fd=descriptor, follow_symlinks=False)
            if stat.S_ISDIR(info.st_mode):
                shutil.rmtree(entry, dir_fd=descriptor)
            else:
                os.unlink(entry, dir_fd=descriptor)
        current = directory.lstat()
        if (current.st_dev, current.st_ino) != identity or stat.S_ISLNK(current.st_mode):
            return False
        # A root-name replacement cannot redirect recursive deletion: rmdir
        # removes only an empty directory and never follows a symlink.
        directory.rmdir()
        return True
    except OSError:
        return False


def main():
    if ctypes.CDLL(None).prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
        return 1
    directory = Path(tempfile.mkdtemp(prefix='owned-browser-', dir=sys.argv[1]))
    descriptor = os.open(directory, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    identity = (os.fstat(descriptor).st_dev, os.fstat(descriptor).st_ino)
    proof_fd = int(sys.argv[2]) if len(sys.argv) > 2 else None
    child = None
    stopped = False
    def stop(*_):
        nonlocal stopped
        stopped = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    try:
        # Playwright creates download/artifact directories outside user_data_dir.
        # Put its whole temporary namespace inside the descriptor-owned root so
        # abrupt worker death cannot leave those files behind in shared /tmp.
        temporary = directory / '.luda-temporary'
        temporary.mkdir(mode=0o700)
        child_environment = dict(os.environ, TMPDIR=str(temporary), TMP=str(temporary), TEMP=str(temporary))
        child = subprocess.Popen([sys.executable, '-m', 'luda._browser_worker', str(directory)],
                                 stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.DEVNULL, start_new_session=True, env=child_environment)
        selector = selectors.DefaultSelector()
        for fd in (sys.stdin.fileno(), sys.stdout.fileno(), child.stdin.fileno(), child.stdout.fileno()):
            os.set_blocking(fd, False)
        selector.register(sys.stdin, selectors.EVENT_READ, 'request')
        selector.register(child.stdout, selectors.EVENT_READ, 'response')
        incoming = b''; response = b''; to_child = b''; to_parent = b''
        deadline = None
        while not stopped:
            if child.poll() is not None or (deadline is not None and time.monotonic() >= deadline):
                break
            if to_child:
                try:
                    count = os.write(child.stdin.fileno(), to_child)
                    to_child = to_child[count:]
                except BlockingIOError:
                    pass
            if to_parent:
                try:
                    count = os.write(sys.stdout.fileno(), to_parent)
                    to_parent = to_parent[count:]
                except BlockingIOError:
                    pass
            for key, _ in selector.select(.02):
                data = os.read(key.fileobj.fileno(), 65536)
                if not data:
                    return 0
                if key.data == 'request':
                    incoming += data
                    if len(incoming) > MAX_PACKET:
                        return 1
                    if b'\n' in incoming:
                        if deadline is not None or to_child or to_parent:
                            return 1
                        line, incoming = incoming.split(b'\n', 1)
                        if incoming:
                            return 1
                        # Fixed framing only; the worker validates operations.
                        json.loads(line)
                        to_child = line + b'\n'
                        deadline = time.monotonic() + 8
                else:
                    response += data
                    if len(response) > MAX_PACKET:
                        return 1
                    if b'\n' in response:
                        line, response = response.split(b'\n', 1)
                        if response or deadline is None:
                            return 1
                        json.loads(line)
                        to_parent = line + b'\n'
                        deadline = None
        return 1
    except (OSError, ValueError):
        return 1
    finally:
        stopped_owned = stop_owned()
        if child:
            for stream in (child.stdin, child.stdout):
                if stream:
                    stream.close()
            try:
                child.wait(timeout=.1)
            except (subprocess.TimeoutExpired, ChildProcessError):
                pass
        removed = clear_profile(directory, descriptor, identity) if stopped_owned else False
        os.close(descriptor)
        if proof_fd is not None:
            try:
                os.write(proof_fd, b'1' if stopped_owned and removed else b'0')
            except OSError:
                pass
            os.close(proof_fd)



if __name__ == '__main__':
    raise SystemExit(main())
