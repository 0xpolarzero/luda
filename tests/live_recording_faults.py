"""Private recorder lifecycle faults: quota, competing client, display change and death."""

import json, os, signal, subprocess, sys, time
from pathlib import Path
from unittest.mock import patch
from luda.desktop import Desktop
from luda.common import DesktopError
from luda import recording

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/recording-faults" / str(time.time_ns())
OUT.mkdir(parents=True)
assert os.getuid() != 0 and os.environ.get("LUDA_ISOLATED_TEST_DISPLAY") == "1"
records = []


def alive(pid):
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0] != "Z"
    except FileNotFoundError:
        return False


def wait(test, seconds=8):
    deadline = time.monotonic() + seconds
    while not test():
        assert time.monotonic() < deadline, (
            "Timed out waiting for owned recording cleanup"
        )
        time.sleep(0.02)


def run():
    keeper = subprocess.Popen(
        ["xfwm4", "--compositor=off"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    wait(lambda: subprocess.run(["wmctrl", "-m"], capture_output=True).returncode == 0)
    first = Desktop()
    second = Desktop()
    try:
        with first.transaction():
            ticket = first.recording("start", max_seconds=10)["recording_id"]
        with second.transaction():
            try:
                second.recording("start", max_seconds=10)
                raise AssertionError("Competing recorder accepted")
            except DesktopError as exc:
                assert exc.code == "RECORDING_BUSY", exc.code
        first.recording("delete", ticket)
        records.append(
            {"case": "cooperating-clients-one-active-recorder", "passed": True}
        )
        with first.transaction():
            ticket = first.recording("start", max_seconds=10)["recording_id"]
        # FFmpeg can finish a playable fragment on an unsolicited interrupt.
        # That must not masquerade as our requested stop or duration limit.
        os.kill(first.recordings.tickets[ticket]["worker_pid"], signal.SIGINT)
        wait(lambda: first.recording("status", ticket)["state"] in ("complete", "failed"))
        interrupted = first.recording("status", ticket)
        assert interrupted["state"] == "failed" and "path" not in interrupted, interrupted
        first.recording("delete", ticket)
        records.append({"case": "unsolicited-recorder-interrupt-refuses-completion", "passed": True})
        before = set(first.runtime.glob("recording-*"))
        with patch.object(recording, "MAX_BYTES", 1024):
            try:
                with first.transaction():
                    value = first.recording("start", max_seconds=3)
                ticket = value["recording_id"]
                wait(lambda: first.recording("status", ticket)["state"] == "failed")
                first.recording("delete", ticket)
            except DesktopError as exc:
                assert exc.code == "RECORDING_FAILED", exc.code
        assert not any(
            (path / "recording.mp4").exists()
            for path in set(first.runtime.glob("recording-*")) - before
        )
        records.append(
            {
                "case": "actual-RLIMIT_FSIZE-refuses-playable-success-and-removes-partial",
                "passed": True,
            }
        )
        with first.transaction():
            ticket = first.recording("start", max_seconds=10)["recording_id"]
        internal = first.recordings.tickets[ticket]
        guardian = internal["process"].pid
        worker = internal["worker_pid"]
        directory = internal["directory"]
        os.kill(guardian, signal.SIGSTOP)
        value = first.recording("delete", ticket)
        assert value["state"] == "deleted"
        wait(lambda: not alive(worker))
        assert not directory.exists()
        records.append(
            {
                "case": "stopped-guardian-delete-reaps-worker-and-removes-file",
                "passed": True,
            }
        )
        with first.transaction():
            ticket = first.recording("start", max_seconds=10)["recording_id"]
        try:
            subprocess.run(
                [
                    "xrandr",
                    "--setmonitor",
                    "LUDA_RECORDING_TEST",
                    "100/26x100/26+0+0",
                    "none",
                ],
                check=True,
                capture_output=True,
            )
            wait(lambda: first.recording("status", ticket)["state"] == "failed")
            assert "path" not in first.recording("status", ticket)
            records.append({"case": "RandR-change-refuses-completion", "passed": True})
        finally:
            subprocess.run(
                ["xrandr", "--delmonitor", "LUDA_RECORDING_TEST"], capture_output=True
            )
            first.recording("delete", ticket)
        # Actual MCP controller death is approximated here by a disposable backend
        # owner process. Its stdin-pipe ownership and guardian are production code.
        script = """import json,sys\nfrom luda.desktop import Desktop\nd=Desktop()\nwith d.transaction():v=d.recording('start',max_seconds=10)\nt=d.recordings.tickets[v['recording_id']]\nprint(json.dumps({'guardian':t['process'].pid,'worker':t['worker_pid'],'directory':str(t['directory'])}),flush=True)\nsys.stdin.buffer.read()\n"""
        owner = subprocess.Popen(
            [sys.executable, "-c", script],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        try:
            import select

            assert select.select([owner.stdout], [], [], 8)[0]
            value = json.loads(owner.stdout.readline())
            os.kill(owner.pid, signal.SIGKILL)
            owner.wait(timeout=3)
            wait(lambda: not alive(value["guardian"]) and not alive(value["worker"]))
            assert not Path(value["directory"]).exists()
            records.append(
                {
                    "case": "owner-SIGKILL-pipe-EOF-cleans-recorder-and-artifact",
                    "passed": True,
                }
            )
        finally:
            if owner.poll() is None:
                owner.kill()
                owner.wait()
            owner.stdin.close()
            owner.stdout.close()
            owner.stderr.close()
    finally:
        first.close()
        second.close()
        keeper.terminate()
        keeper.wait(timeout=3)


try:
    run()
finally:
    (OUT / "result.json").write_text(json.dumps(records, indent=2) + "\n")
print(json.dumps(records))
