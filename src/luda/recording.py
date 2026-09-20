"""Explicit bounded recording tickets; every artifact is temporary and session-owned."""

import json
import os
from pathlib import Path
import selectors
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from .common import DesktopError, checkpoint, mark_effect, stop_process
from .storage import storage_errors
from .timing import elapsed_time

MAX_BYTES = 64 * 1024 * 1024


class Recordings:
    def __init__(self, desktop):
        self.desktop = desktop
        self.tickets = {}
        self.lock = threading.Lock()

    def drain(self, ticket):
        process = ticket["process"]
        while not process.stdout.closed:
            try:
                chunk = os.read(process.stdout.fileno(), 4096)
            except BlockingIOError:
                break
            if not chunk:
                break
            ticket["buffer"] += chunk
            if len(ticket["buffer"]) > 16384:
                raise DesktopError(
                    "RECORDING_FAILED",
                    "Recording supervisor returned invalid metadata.",
                )
            while b"\n" in ticket["buffer"]:
                line, ticket["buffer"] = ticket["buffer"].split(b"\n", 1)
                value = json.loads(line)
                if value.get("state") not in (
                    "starting",
                    "recording",
                    "finalizing",
                    "complete",
                    "failed",
                ):
                    raise DesktopError(
                        "RECORDING_FAILED",
                        "Recording supervisor returned invalid state.",
                    )
                for field in ("artifact_identity", "worker_pid", "worker_start"):
                    if field in value:
                        ticket[field] = value.pop(field)
                ticket["status"] = value
        if process.poll() is not None and ticket["status"]["state"] not in (
            "failed",
            "deleted",
        ):
            ticket["status"] = {"state": "failed", "code": "RECORDING_FAILED"}
        return ticket["status"]

    def describe(self, recording_id, ticket):
        value = dict(self.drain(ticket))
        result = {
            "recording_id": recording_id,
            "effect": "none",
            **value,
            "retention": "Temporary until explicit delete, backend close/reconnect or server death; copy elsewhere explicitly for durable saving.",
        }
        if value["state"] == "complete":
            path = ticket["directory"] / "recording.mp4"
            try:
                current = path.lstat()
                if (current.st_dev, current.st_ino) != tuple(
                    ticket.get("artifact_identity", ())
                ):
                    raise OSError()
            except OSError:
                return {
                    "recording_id": recording_id,
                    "effect": "none",
                    "state": "failed",
                    "code": "RECORDING_FAILED",
                }
            result["path"] = str(path)
        return result

    def start(self, max_seconds):
        if type(max_seconds) is not int or not 1 <= max_seconds <= 60:
            raise DesktopError(
                "INVALID_ARGUMENT", "max_seconds must be an integer from 1 to 60."
            )
        if len(self.tickets) >= 4:
            raise DesktopError(
                "RECORDING_LIMIT",
                "Delete an existing temporary recording before creating another; maximum four tickets.",
            )
        active = 0
        retained = 0
        for ticket in self.tickets.values():
            status = self.drain(ticket)
            active += status["state"] in ("starting", "recording", "finalizing")
            retained += status.get("bytes", 0)
        if active:
            raise DesktopError(
                "RECORDING_BUSY", "This backend already has an active recording."
            )
        if retained + MAX_BYTES > 128 * 1024 * 1024:
            raise DesktopError(
                "RECORDING_LIMIT",
                "Temporary recording storage reservation exceeds 128 MiB; explicitly delete an existing recording.",
            )
        environment = self.desktop.environment
        ffmpeg = shutil.which("ffmpeg", path=environment.get("PATH", os.defpath))
        ffprobe = shutil.which("ffprobe", path=environment.get("PATH", os.defpath))
        if not ffmpeg or not ffprobe:
            raise DesktopError(
                "RECORDING_UNAVAILABLE",
                "Optional local ffmpeg and ffprobe are required; other desktop tools remain usable.",
            )
        topology = self.desktop.display().topology()
        native = topology["root"]
        width, height = native["width"], native["height"]
        if width <= 0 or height <= 0 or width * height > 32_000_000:
            raise DesktopError(
                "RECORDING_LIMIT", "Capture is limited to 32 million native pixels."
            )
        scale = min(1, 1280 / width, 720 / height)
        image = [
            max(2, int(width * scale) // 2 * 2),
            max(2, int(height * scale) // 2 * 2),
        ]
        directory = None
        process = None
        identity = uuid.uuid4().hex
        try:
            with storage_errors("create temporary recording"):
                directory = Path(
                    tempfile.mkdtemp(prefix="recording-", dir=self.desktop.runtime)
                )
                name = Path(self.desktop.control.path).name
                request = {
                    "directory": str(directory),
                    "lock": str(self.desktop.runtime / (name + ".recording.lock")),
                    "topology": topology,
                    "native": [width, height],
                    "image": image,
                    "max_seconds": max_seconds,
                    "max_bytes": MAX_BYTES,
                    "ffmpeg": ffmpeg,
                    "ffprobe": ffprobe,
                }
                process = subprocess.Popen(
                    [sys.executable, "-m", "luda._recording_guard"],
                    stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    env=dict(environment),
                    start_new_session=True,
                )
                os.set_blocking(process.stdout.fileno(), False)
                ticket = {
                    "process": process,
                    "directory": directory,
                    "status": {"state": "starting"},
                    "buffer": b"",
                }
                self.tickets[identity] = ticket
                process.stdin.write(json.dumps(request).encode() + b"\n")
                process.stdin.flush()
        except BaseException:
            if identity in self.tickets:
                self.delete(identity)
            elif directory is not None:
                try:
                    directory.rmdir()
                except OSError:
                    pass
            raise
        try:
            deadline = elapsed_time() + 4
            while self.drain(ticket)["state"] == "starting":
                checkpoint()
                if elapsed_time() >= deadline:
                    raise DesktopError(
                        "RECORDING_FAILED",
                        "Recording did not start within its deadline.",
                    )
                time.sleep(0.02)
            value = self.describe(identity, ticket)
            if value["state"] == "failed":
                raise DesktopError(
                    value.get("code", "RECORDING_FAILED"),
                    "Recording could not start; no completed recording is available.",
                )
            mark_effect("dispatched")
            value["effect"] = "dispatched"
            return value
        except BaseException:
            self.delete(identity)
            raise

    def delete(self, identity):
        ticket = self.tickets[identity]
        process = ticket["process"]
        try:
            self.drain(ticket)
        except (ValueError, KeyError, TypeError, DesktopError):
            # Untrusted/malformed supervisor output must never prevent cleanup.
            pass
        try:
            if process.poll() is None:
                try:
                    process.stdin.close()
                except OSError:
                    pass
                try:
                    process.wait(timeout=4)
                except subprocess.TimeoutExpired:
                    stop_process(process)
        finally:
            process.stdout.close()
            worker = ticket.get("worker_pid")
            start = ticket.get("worker_start")

            def worker_alive():
                if not worker:
                    return False
                try:
                    fields = (
                        Path(f"/proc/{worker}/stat")
                        .read_text()
                        .rsplit(")", 1)[1]
                        .split()
                    )
                    return fields[0] != "Z" and fields[19] == start
                except OSError:
                    return False

            deadline = elapsed_time() + 2
            while worker_alive() and elapsed_time() < deadline:
                time.sleep(0.01)
            if worker_alive():
                raise DesktopError(
                    "RECORDING_FAILED",
                    "Recording worker cleanup remains unconfirmed; do not start another recording.",
                )
            artifact_identity = ticket.get("artifact_identity")
            path = ticket["directory"] / "recording.mp4"
            if artifact_identity:
                from ._recording_guard import unlink_owned

                unlink_owned(path, tuple(artifact_identity))
            try:
                ticket["directory"].rmdir()
            except OSError:
                pass
            self.tickets.pop(identity, None)
        return {
            "recording_id": identity,
            "effect": "verified",
            "state": "deleted",
            "verification": "Owned supervisor exited; original artifact path removed if still owned. Any replacement or added files were preserved.",
        }

    def action(self, action, recording_id=None, max_seconds=30):
        with self.lock:
            if action == "start":
                if recording_id is not None:
                    raise DesktopError(
                        "INVALID_ARGUMENT", "start takes no recording_id."
                    )
                return self.start(max_seconds)
            if action not in ("status", "stop", "delete"):
                raise DesktopError(
                    "INVALID_ARGUMENT", "Choose start, status, stop or delete."
                )
            if recording_id not in self.tickets:
                raise DesktopError(
                    "STALE_TARGET", "Recording ticket is unknown to this backend."
                )
            if max_seconds != 30:
                raise DesktopError(
                    "INVALID_ARGUMENT", "max_seconds applies only to start."
                )
            ticket = self.tickets[recording_id]
            if action == "delete":
                return self.delete(recording_id)
            if action == "stop" and self.drain(ticket)["state"] in (
                "starting",
                "recording",
            ):
                try:
                    ticket["process"].stdin.write(b"stop\n")
                    ticket["process"].stdin.flush()
                except OSError:
                    pass
                deadline = elapsed_time() + 9
                while (
                    self.drain(ticket)["state"] not in ("complete", "failed")
                    and elapsed_time() < deadline
                ):
                    time.sleep(0.02)
            return self.describe(recording_id, ticket)

    def close(self):
        with self.lock:
            errors = []
            for identity in list(self.tickets):
                try:
                    self.delete(identity)
                except Exception as exc:
                    errors.append(exc)
            if errors:
                raise errors[0]
