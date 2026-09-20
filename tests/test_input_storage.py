"""Pre-spawn private-input failures retain accurate effects and actionable errors."""

from contextlib import nullcontext
import errno
import json
import threading
import unittest
from unittest.mock import Mock, patch
from luda import common, server
from luda.common import DesktopError, operation_scope, mark_effect


class InputStorageTests(unittest.TestCase):
    def backend(self):
        backend = Mock()
        backend.transaction.return_value = nullcontext()
        backend.ocr.side_effect = lambda: common.run(
            ["/bin/cat"], data=b"SYNTHETIC_PAYLOAD"
        )
        return backend

    def test_public_creation_write_flush_seek_faults_are_pre_spawn_and_redacted(self):
        for number in (
            errno.ENOSPC,
            errno.EDQUOT,
            errno.EROFS,
            errno.EACCES,
            errno.EIO,
        ):
            for stage in ("create", "write", "flush", "seek"):
                with self.subTest(errno=number, stage=stage):
                    source = Mock()
                    fault = OSError(number, "SYNTHETIC_SENSITIVE")
                    if stage != "create":
                        getattr(source, stage).side_effect = fault
                    with (
                        patch.object(
                            server, "get_backend", return_value=self.backend()
                        ),
                        patch.object(
                            common.tempfile,
                            "TemporaryFile",
                            return_value=source,
                            side_effect=fault if stage == "create" else None,
                        ),
                        patch.object(common.subprocess, "Popen") as spawn,
                    ):
                        response = server.execute("ocr")
                        result = json.loads(response.content[0].text)
                    self.assertTrue(response.isError)
                    self.assertEqual(result["code"], "STORAGE_UNAVAILABLE")
                    self.assertEqual(result["effect"], "none")
                    spawn.assert_not_called()
                    self.assertNotIn("SYNTHETIC", json.dumps(result))
                    self.assertNotIn("SYNTHETIC", json.dumps(server._history[-1]))
                    self.assertEqual(
                        source.close.call_count, 0 if stage == "create" else 1
                    )

    def test_second_close_fault_cannot_mask_cancel_or_original_storage_error(self):
        for cancel in (False, True):
            cancelled = threading.Event()
            source = Mock()

            def fail(data):
                if cancel:
                    cancelled.set()
                raise OSError(errno.ENOSPC, "FIRST_PRIVATE")

            source.write.side_effect = fail
            source.close.side_effect = OSError(errno.EIO, "SECOND_PRIVATE")
            with (
                operation_scope(cancelled=cancelled),
                patch.object(common.tempfile, "TemporaryFile", return_value=source),
                patch.object(common.subprocess, "Popen") as spawn,
                self.assertRaises(DesktopError) as caught,
            ):
                common.run(["/bin/cat"], data=b"private")
            self.assertEqual(
                caught.exception.code, "CANCELLED" if cancel else "STORAGE_UNAVAILABLE"
            )
            self.assertEqual(caught.exception.effect, "none")
            spawn.assert_not_called()
            source.close.assert_called_once()
            self.assertNotIn("PRIVATE", str(caught.exception))

    def test_prior_effect_preserved_and_overall_deadline_precedes_storage_error(self):
        for expired in (False, True):
            source = Mock()
            with operation_scope() as operation:
                mark_effect()

                def fail(data):
                    if expired:
                        operation.deadline = 0
                    raise OSError(errno.EDQUOT, "private")

                source.write.side_effect = fail
                with (
                    patch.object(common.tempfile, "TemporaryFile", return_value=source),
                    patch.object(common.subprocess, "Popen") as spawn,
                    self.assertRaises(DesktopError) as caught,
                ):
                    common.run(["/bin/cat"], data=b"private")
            self.assertEqual(
                caught.exception.code, "TIMEOUT" if expired else "STORAGE_UNAVAILABLE"
            )
            self.assertEqual(caught.exception.effect, "uncertain")
            spawn.assert_not_called()

    def test_cancellation_after_successful_staging_prevents_spawn(self):
        cancelled = threading.Event()
        source = Mock()
        source.flush.side_effect = cancelled.set
        with (
            operation_scope(cancelled=cancelled),
            patch.object(common.tempfile, "TemporaryFile", return_value=source),
            patch.object(common.subprocess, "Popen") as spawn,
            self.assertRaises(DesktopError) as caught,
        ):
            common.run(["/bin/cat"], data=b"private")
        self.assertEqual(caught.exception.code, "CANCELLED")
        spawn.assert_not_called()
        source.close.assert_called_once()

    def test_real_temporary_descriptor_closes_after_injected_buffered_fault(self):
        import os

        source = common.tempfile.TemporaryFile()
        descriptor = source.fileno()
        wrapped = Mock(wraps=source)
        wrapped.write.side_effect = OSError(errno.ENOSPC, "private")

        def close():
            source.close()
            raise OSError(errno.ENOSPC, "repeated buffered flush failure")

        wrapped.close.side_effect = close
        with (
            patch.object(common.tempfile, "TemporaryFile", return_value=wrapped),
            patch.object(common.subprocess, "Popen") as spawn,
            self.assertRaises(DesktopError) as caught,
        ):
            common.run(["/bin/cat"], data=b"private")
        self.assertEqual(caught.exception.code, "STORAGE_UNAVAILABLE")
        spawn.assert_not_called()
        self.assertTrue(source.closed)
        with self.assertRaises(OSError) as closed:
            os.fstat(descriptor)
        self.assertEqual(closed.exception.errno, errno.EBADF)
