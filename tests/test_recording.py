import errno, json, os, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from luda.common import DesktopError
from luda.recording import Recordings
from luda._recording_guard import unlink_owned
from luda import server


class RecordingTests(unittest.TestCase):
    def manager(self):
        d = SimpleNamespace(
            environment={"PATH": "/usr/bin"},
            runtime=Path("/tmp"),
            control=SimpleNamespace(path=Path("/tmp/display.control.json")),
        )
        return Recordings(d)

    def test_invalid_duration_and_missing_dependency_do_not_spawn(self):
        manager = self.manager()
        for seconds in (True, 0, 61, 1.5):
            with (
                patch("luda.recording.subprocess.Popen") as spawn,
                self.assertRaises(DesktopError),
            ):
                manager.action("start", max_seconds=seconds)
            spawn.assert_not_called()
        with (
            patch("luda.recording.shutil.which", return_value=None),
            patch("luda.recording.subprocess.Popen") as spawn,
            self.assertRaises(DesktopError) as caught,
        ):
            manager.action("start")
        self.assertEqual(caught.exception.code, "RECORDING_UNAVAILABLE")
        spawn.assert_not_called()

    def test_limits_and_unknown_tickets_are_explicit(self):
        manager = self.manager()
        manager.tickets = {str(i): {} for i in range(4)}
        with self.assertRaises(DesktopError) as caught:
            manager.action("start")
        self.assertEqual(caught.exception.code, "RECORDING_LIMIT")
        for action in ("status", "stop", "delete"):
            with self.assertRaises(DesktopError) as caught:
                manager.action(action, "unknown")
            self.assertEqual(caught.exception.code, "STALE_TARGET")

    def test_delete_only_original_inode_and_preserve_user_file(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "recording.mp4"
            path.write_bytes(b"owned")
            st = path.stat()
            identity = (st.st_dev, st.st_ino)
            path.rename(path.with_name("kept-original"))
            path.write_bytes(b"user replacement")
            unlink_owned(path, identity)
            self.assertEqual(path.read_bytes(), b"user replacement")
            st = path.stat()
            unlink_owned(path, (st.st_dev, st.st_ino))
            self.assertFalse(path.exists())

    def test_cleanup_dispatch_bypasses_pause_quarantine_and_active_operation_gate(self):
        backend = Mock()
        backend.recording.return_value = {"state": "deleted", "effect": "verified"}
        server._operation_gate.acquire()
        server._quarantined.set()
        try:
            with (
                patch.object(server, "get_backend", return_value=backend),
                patch.object(server, "require_session_input") as guard,
            ):
                result = server.execute("recording", "delete", "owned", 30)
            self.assertFalse(result.isError)
            backend.recording.assert_called_once_with("delete", "owned", 30)
            guard.assert_not_called()
            backend.transaction.assert_not_called()
            backend.control.require_active.assert_not_called()
        finally:
            server._quarantined.clear()
            server._operation_gate.release()

    def test_start_remains_blocked_during_quarantine(self):
        server._quarantined.set()
        try:
            with patch.object(server, "get_backend") as backend:
                result = server.execute("recording", "start", None, 30)
            self.assertTrue(result.isError)
            self.assertEqual(json.loads(result.content[0].text)["code"], "BUSY")
            backend.assert_not_called()
        finally:
            server._quarantined.clear()

    def test_storage_failure_before_spawn_is_typed(self):
        manager = self.manager()
        manager.desktop.display = lambda: SimpleNamespace(
            topology=lambda: {"root": {"width": 100, "height": 100}}
        )
        with (
            patch("luda.recording.shutil.which", return_value="/usr/bin/ffmpeg"),
            patch(
                "luda.recording.tempfile.mkdtemp",
                side_effect=OSError(errno.ENOSPC, "SENSITIVE"),
            ),
            patch("luda.recording.subprocess.Popen") as spawn,
            self.assertRaises(DesktopError) as caught,
        ):
            manager.action("start")
        self.assertEqual(caught.exception.code, "STORAGE_UNAVAILABLE")
        self.assertNotIn("SENSITIVE", str(caught.exception))
        spawn.assert_not_called()

    def test_spawn_failure_removes_only_new_empty_directory(self):
        manager = self.manager()
        manager.desktop.display = lambda: SimpleNamespace(
            topology=lambda: {"root": {"width": 100, "height": 100}}
        )
        with tempfile.TemporaryDirectory() as directory:
            manager.desktop.runtime = Path(directory)
            with (
                patch("luda.recording.shutil.which", return_value="/usr/bin/ffmpeg"),
                patch(
                    "luda.recording.subprocess.Popen",
                    side_effect=OSError(errno.EMFILE, "SENSITIVE"),
                ),
                self.assertRaises(DesktopError),
            ):
                manager.action("start")
            self.assertEqual(list(Path(directory).iterdir()), [])
            self.assertEqual(manager.tickets, {})

    def test_parent_death_setup_rejects_reparented_child_and_prctl_failure(self):
        from luda._recording_guard import child_setup

        for actual_parent, prctl_result in ((1, 0), (42, -1)):
            with self.subTest(actual_parent=actual_parent, prctl_result=prctl_result):
                with (
                    patch(
                        "luda._recording_guard.os.getppid", return_value=actual_parent
                    ),
                    patch("luda._recording_guard.C.CDLL") as libc,
                    patch(
                        "luda._recording_guard.os._exit",
                        side_effect=RuntimeError("exited"),
                    ) as exiting,
                    patch("luda._recording_guard.resource.setrlimit") as limit,
                ):
                    libc.return_value.prctl.return_value = prctl_result
                    with self.assertRaisesRegex(RuntimeError, "exited"):
                        child_setup(1024, 42)
                    exiting.assert_called_once_with(127)
                    limit.assert_not_called()

    def test_malformed_supervisor_output_does_not_skip_cleanup(self):
        manager = self.manager()
        with tempfile.TemporaryDirectory() as directory:
            owned = Path(directory) / "owned"
            owned.mkdir()
            process = Mock()
            process.poll.return_value = 0
            manager.tickets["ticket"] = {"directory": owned, "process": process}
            with patch.object(manager, "drain", side_effect=ValueError("malformed")):
                value = manager.delete("ticket")
            self.assertEqual(value["state"], "deleted")
            self.assertFalse(owned.exists())
            process.stdout.close.assert_called_once()
