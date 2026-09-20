"""Private recorder owner: controller EOF stops capture and removes exact owned files."""

import ctypes as C
import fcntl
import json
import os
from pathlib import Path
import resource
import selectors
import signal
import subprocess
import sys
import tempfile
import time
from .timing import elapsed_time


def child_setup(limit, expected_parent):
    # Runs only in this single-threaded private supervisor's child.
    if C.CDLL(None).prctl(1, signal.SIGKILL) != 0:
        os._exit(127)
    if os.getppid() != expected_parent:
        os._exit(127)
    resource.setrlimit(resource.RLIMIT_FSIZE, (limit, limit))


def stop(process):
    interrupted = False
    if process and process.poll() is None:
        try:
            os.killpg(process.pid, signal.SIGINT)
            interrupted = True
        except ProcessLookupError:
            pass
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait(timeout=2)
    return interrupted


def emit(value):
    print(json.dumps(value, separators=(",", ":")), flush=True)


def unlink_owned(path, identity):
    try:
        current = path.lstat()
        if (current.st_dev, current.st_ino) == identity:
            path.unlink()
    except FileNotFoundError:
        pass


def main():
    guardian_pid = os.getpid()
    request = json.loads(sys.stdin.buffer.readline(65537))
    directory = Path(request["directory"])
    path = directory / "recording.mp4"
    output = None
    identity = None
    process = None
    lock = None
    stop_requested = False
    selector = selectors.DefaultSelector()
    selector.register(sys.stdin.fileno(), selectors.EVENT_READ, "control")
    os.set_blocking(sys.stdin.fileno(), False)

    def control():
        nonlocal stop_requested
        data = os.read(sys.stdin.fileno(), 4096)
        if not data:
            raise EOFError()
        stop_requested = True
        return "delete" if b"delete" in data else "stop"

    def check_command(argv, timeout, data=None):
        with tempfile.TemporaryFile(dir=directory) as captured:
            child = subprocess.Popen(
                argv,
                stdin=subprocess.PIPE if data is not None else subprocess.DEVNULL,
                stdout=captured,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                pass_fds=(output,),
                preexec_fn=lambda: child_setup(65536, guardian_pid),
            )
            if data is not None:
                child.stdin.write(data)
                child.stdin.close()
            deadline = elapsed_time() + timeout
            try:
                while child.poll() is None:
                    if elapsed_time() >= deadline:
                        raise TimeoutError()
                    for key, _ in selector.select(0.05):
                        if key.data == "control" and control() == "delete":
                            raise EOFError()
                if child.returncode:
                    raise ValueError("verification failed")
                captured.seek(0)
                data = captured.read(65537)
                if len(data) > 65536:
                    raise ValueError("verification limit")
                return data
            finally:
                stop(child)

    try:
        lock = os.open(request["lock"], os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            emit({"state": "failed", "code": "RECORDING_BUSY"})
            return
        output = os.open(
            path, os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600
        )
        st = os.fstat(output)
        identity = (st.st_dev, st.st_ino)
        emit({"state": "starting", "artifact_identity": list(identity)})

        def topology_matches():
            raw = check_command(
                [sys.executable, "-m", "luda._x11_helper"], 2, b'{"method":"topology"}'
            )
            return json.loads(raw).get("result") == request["topology"]

        if not topology_matches():
            raise ValueError("display changed")
        width, height = request["native"]
        ow, oh = request["image"]
        argv = [
            request["ffmpeg"],
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-f",
            "x11grab",
            "-framerate",
            "10",
            "-video_size",
            f"{width}x{height}",
            "-i",
            os.environ["DISPLAY"],
            "-an",
            "-vf",
            f"scale={ow}:{oh}",
            "-c:v",
            "mpeg4",
            "-q:v",
            "5",
            "-pix_fmt",
            "yuv420p",
            "-threads",
            "1",
            "-t",
            str(request["max_seconds"]),
            "-movflags",
            "+frag_keyframe+empty_moov",
            "-f",
            "mp4",
            "-progress",
            "pipe:1",
            "-stats_period",
            "0.1",
            f"pipe:{output}",
        ]
        process = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
            pass_fds=(output, lock),
            preexec_fn=lambda: child_setup(request["max_bytes"], guardian_pid),
        )
        worker_start = (
            Path(f"/proc/{process.pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
        )
        emit(
            {
                "state": "starting",
                "worker_pid": process.pid,
                "worker_start": worker_start,
            }
        )
        os.set_blocking(process.stdout.fileno(), False)
        selector.register(process.stdout, selectors.EVENT_READ, "progress")
        deadline = elapsed_time() + request["max_seconds"]
        buffer = b""
        started = False
        reason = "duration_limit"
        last_frames = 0
        next_topology = elapsed_time() + 0.5
        while process.poll() is None:
            if elapsed_time() >= deadline:
                break
            if elapsed_time() >= next_topology:
                if not topology_matches():
                    raise ValueError("display changed")
                next_topology = elapsed_time() + 0.5
            if stop_requested:
                reason = "requested_stop"
                break
            ending = False
            for key, _ in selector.select(0.05):
                if key.data == "control":
                    action = control()
                    if action == "delete":
                        raise EOFError()
                    reason = "requested_stop"
                    ending = True
                    break
                if key.data == "progress":
                    chunk = os.read(process.stdout.fileno(), 4096)
                    if not chunk:
                        selector.unregister(process.stdout)
                        continue
                    buffer += chunk
                    if len(buffer) > 16384:
                        raise ValueError("progress limit")
                    while b"\n" in buffer:
                        line, buffer = buffer.split(b"\n", 1)
                        if line.startswith(b"frame="):
                            frames = int(line[6:])
                            last_frames = max(frames, last_frames)
                            if frames > 0 and not started:
                                emit({"state": "recording", "frames_captured": frames})
                                started = True
            if ending:
                break
        interrupted = stop(process)
        if not topology_matches():
            raise ValueError("display changed")
        try:
            selector.unregister(process.stdout)
        except KeyError:
            pass
        process.stdout.close()
        if (process.returncode not in (0, 255)
                or (process.returncode == 255 and not interrupted)
                or not started):
            raise ValueError("capture failed")
        os.fsync(output)
        emit({"state": "finalizing"})
        raw = check_command(
            [
                request["ffprobe"],
                "-v",
                "error",
                "-show_entries",
                "stream=codec_type,width,height",
                "-of",
                "json",
                f"/proc/self/fd/{output}",
            ],
            3,
        )
        streams = json.loads(raw)["streams"]
        if len(streams) != 1 or streams[0] != {
            "codec_type": "video",
            "width": ow,
            "height": oh,
        }:
            raise ValueError("stream mismatch")
        check_command(
            [
                request["ffmpeg"],
                "-v",
                "error",
                "-xerror",
                "-i",
                f"/proc/self/fd/{output}",
                "-map",
                "0:v:0",
                "-f",
                "null",
                "-",
            ],
            6,
        )
        current = path.lstat()
        if (current.st_dev, current.st_ino) != identity:
            raise ValueError("artifact replaced")
        size = os.fstat(output).st_size
        if not 0 < size <= request["max_bytes"]:
            raise ValueError("size limit")
        fcntl.flock(lock, fcntl.LOCK_UN)
        os.close(lock)
        lock = None
        emit(
            {
                "state": "complete",
                "bytes": size,
                "image_size": {"width": ow, "height": oh},
                "end_reason": reason,
                "playable_verified": True,
            }
        )
        while True:
            for key, _ in selector.select(0.1):
                if key.data == "control" and control() == "delete":
                    raise EOFError()
    except EOFError:
        pass
    except Exception:
        try:
            emit({"state": "failed", "code": "RECORDING_FAILED"})
        except (BrokenPipeError, OSError):
            pass
        # Keep lifecycle ownership until delete/EOF, but failed partials go now.
        if identity:
            unlink_owned(path, identity)
            identity = None
    finally:
        stop(process)
        if output is not None:
            os.close(output)
        if identity:
            unlink_owned(path, identity)
        if lock is not None:
            os.close(lock)
        selector.close()
        try:
            directory.rmdir()
        except OSError:
            pass  # User-added files are never recursively deleted.


if __name__ == "__main__":
    main()
