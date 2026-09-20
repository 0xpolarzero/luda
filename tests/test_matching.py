import asyncio, io, json, threading, unittest
from unittest.mock import Mock, patch
from PIL import Image, ImageDraw
from luda import matching, server
from luda.common import DesktopError, operation_scope
from luda.desktop import Desktop
from luda.timing import elapsed_time


def snapshot(size=(80, 60)):
    image = Image.new("RGB", size, "white")
    ImageDraw.Draw(image).rectangle((1, 1, 10, 12), fill="red")
    out = io.BytesIO()
    image.save(out, format="PNG")
    return {"png": out.getvalue(), "image": size, "native": size}


class MatchingTests(unittest.TestCase):
    def setUp(self):
        self.source = snapshot()
        self.bounds = {"x": 0, "y": 0, "width": 16, "height": 16}

    def test_bad_threshold_bounds_limits_rejected_before_worker(self):
        for value in (float("nan"), float("inf"), -0.1, 1.1, True):
            with patch("luda.matching.run") as run, self.assertRaises(DesktopError):
                matching.match(self.source, self.source, self.bounds, value, 20)
            run.assert_not_called()
        for bounds in (
            {"x": 0},
            dict(self.bounds, width=7),
            dict(self.bounds, x=-1),
            dict(self.bounds, x=True),
        ):
            with patch("luda.matching.run") as run, self.assertRaises(DesktopError):
                matching.match(self.source, self.source, bounds, 0.95, 20)
            run.assert_not_called()

    def test_scale_mismatch_and_pixel_budget_before_worker(self):
        for target, code in (
            (dict(self.source, native=(160, 120)), "MATCH_SCALE_MISMATCH"),
            (dict(self.source, image=(3000, 3000), native=(3000, 3000)), "MATCH_LIMIT"),
        ):
            with (
                patch("luda.matching.run") as run,
                self.assertRaises(DesktopError) as caught,
            ):
                matching.match(self.source, target, self.bounds, 0.95, 20)
            self.assertEqual(caught.exception.code, code)
            run.assert_not_called()

    def test_optional_absence_and_flat_template_are_precise(self):
        for code in ("MATCH_UNAVAILABLE", "MATCH_FLAT_TEMPLATE"):
            with (
                patch(
                    "luda.matching.run",
                    return_value=json.dumps({"error": code}).encode(),
                ),
                self.assertRaises(DesktopError) as caught,
            ):
                matching.match(self.source, self.source, self.bounds, 0.95, 20)
            self.assertEqual(caught.exception.code, code)

    def test_malformed_score_box_and_metadata_refused(self):
        candidate = {"image_bounds": self.bounds, "score": 0.99}
        for result in (
            {"candidates": [dict(candidate, score=float("nan"))], "truncated": False},
            {
                "candidates": [dict(candidate, image_bounds=dict(self.bounds, x=90))],
                "truncated": False,
            },
            {"candidates": [], "truncated": "secret"},
            [],
        ):
            with (
                patch("luda.matching.run", return_value=json.dumps(result).encode()),
                self.assertRaises(DesktopError) as caught,
            ):
                matching.match(self.source, self.source, self.bounds, 0.95, 20)
            self.assertEqual(caught.exception.code, "MATCH_FAILED")

    def test_worker_contract_is_bounded_and_no_paths_from_caller(self):
        with patch(
            "luda.matching.run", return_value=b'{"candidates":[],"truncated":false}'
        ) as run:
            self.assertEqual(
                matching.match(self.source, self.source, self.bounds, 0.95, 20)[
                    "candidates"
                ],
                [],
            )
        self.assertEqual(run.call_args.kwargs["timeout"], 3)
        self.assertEqual(run.call_args.kwargs["max_output_bytes"], 65536)
        self.assertIsInstance(run.call_args.kwargs["data"], bytes)

    def driver(self):
        d = Desktop()
        self.addCleanup(d.close)
        d.x = Mock()
        d.x.topology.return_value = {"server_generation": "one", "id": 1}
        d.list_windows = Mock(return_value=[])
        d.observe_popups = Mock(return_value=[])
        d.snapshots["owned"] = {
            **self.source,
            "time": elapsed_time(),
            "signature": d.signature([]),
            "popups": [],
            "topology": {"server_generation": "one", "id": 1},
        }
        return d

    def test_stale_before_and_changed_during_matching_refused(self):
        d = self.driver()

        def changed(*args):
            d.x.topology.return_value = {"server_generation": "one", "id": 2}
            return {"candidates": []}

        with (
            patch("luda.matching.match", side_effect=changed),
            self.assertRaises(DesktopError) as caught,
        ):
            d.match_image("owned", self.bounds, "owned")
        self.assertEqual(caught.exception.code, "STALE_OBSERVATION")
        with patch("luda.matching.match") as match, self.assertRaises(DesktopError):
            d.match_image("owned", self.bounds, "owned")
        match.assert_not_called()

    def test_public_schema_read_only_and_cancellation_before_work(self):
        tool = next(
            t
            for t in asyncio.run(server.mcp.list_tools())
            if t.name == "desktop_match_image"
        )
        self.assertTrue(tool.annotations.readOnlyHint)
        cancelled = threading.Event()
        cancelled.set()
        with (
            operation_scope(cancelled=cancelled),
            self.assertRaises(DesktopError) as caught,
        ):
            matching.match(self.source, self.source, self.bounds, 0.95, 20)
        self.assertEqual(caught.exception.code, "CANCELLED")

    def test_actual_child_cancel_is_reaped_before_late_effect(self):
        import os, tempfile, time
        from pathlib import Path
        from luda.common import run as bounded_run

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            started = root / "started"
            late = root / "late"
            worker = root / "worker.py"
            worker.write_text(
                "import os,time\nfrom pathlib import Path\nPath("
                + repr(str(started))
                + ").write_text(str(os.getpid()))\ntime.sleep(2)\nPath("
                + repr(str(late))
                + ").touch()\n"
            )
            cancelled = threading.Event()

            def cancel_after_start():
                deadline = time.monotonic() + 2
                while not started.exists() and time.monotonic() < deadline:
                    time.sleep(0.005)
                cancelled.set()

            watcher = threading.Thread(target=cancel_after_start)
            watcher.start()

            def substitute(argv, **kwargs):
                return bounded_run(["/usr/bin/python3", str(worker)], **kwargs)

            try:
                with (
                    patch("luda.matching.run", side_effect=substitute),
                    operation_scope(cancelled=cancelled),
                    self.assertRaises(DesktopError) as caught,
                ):
                    matching.match(self.source, self.source, self.bounds, 0.95, 20)
                self.assertEqual(caught.exception.code, "CANCELLED")
                self.assertTrue(started.exists())
                self.assertFalse(late.exists())
                with self.assertRaises(ProcessLookupError):
                    os.kill(int(started.read_text()), 0)
            finally:
                watcher.join(timeout=3)

    def test_engine_fault_sanitized_preserving_timeout_and_output_bounds(self):
        for code in ("BACKEND_ERROR", "TIMEOUT", "OUTPUT_LIMIT"):
            with (
                patch("luda.matching.run", side_effect=DesktopError(code, "SENSITIVE")),
                self.assertRaises(DesktopError) as caught,
            ):
                matching.match(self.source, self.source, self.bounds, 0.95, 20)
            self.assertEqual(
                caught.exception.code,
                "MATCH_FAILED" if code == "BACKEND_ERROR" else code,
            )
            if code == "BACKEND_ERROR":
                self.assertNotIn("SENSITIVE", str(caught.exception))

    def test_template_generation_expiry_and_cached_ownership(self):
        d = self.driver()
        d.snapshots["target"] = {**d.snapshots["owned"]}
        d.snapshots["owned"]["topology"] = {"server_generation": "old"}
        with (
            patch("luda.matching.match") as worker,
            self.assertRaises(DesktopError) as caught,
        ):
            d.match_image("owned", self.bounds, "target")
        self.assertEqual(caught.exception.code, "STALE_OBSERVATION")
        worker.assert_not_called()
        d.snapshots["owned"]["time"] -= 20
        with patch("luda.matching.match") as worker, self.assertRaises(DesktopError):
            d.match_image("owned", self.bounds, "target")
        worker.assert_not_called()
        self.assertNotIn("owned", d.snapshots)

    def test_historical_source_layout_is_not_current_target_requirement(self):
        d = self.driver()
        d.snapshots["target"] = {**d.snapshots["owned"]}
        d.snapshots["owned"]["signature"] = "old-layout"
        with patch(
            "luda.matching.match", return_value={"candidates": [], "truncated": False}
        ) as worker:
            value = d.match_image("owned", self.bounds, "target")
        worker.assert_called_once()
        self.assertEqual(value["effect"], "none")
