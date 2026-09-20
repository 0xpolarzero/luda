"""Actual MCP optional image matching against independently located owned GTK icons."""

import asyncio, json, os, subprocess, sys, time
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/matching" / str(time.time_ns())
OUT.mkdir(parents=True)
assert os.getuid() != 0 and os.environ.get("LUDA_ISOLATED_TEST_DISPLAY") == "1"


async def main():
    processes = []
    results = []
    try:
        wm = subprocess.Popen(
            ["xfwm4", "--compositor=off"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        processes.append(wm)
        for _ in range(80):
            if subprocess.run(["wmctrl", "-m"], capture_output=True).returncode == 0:
                break
            await asyncio.sleep(0.05)
        fixture = subprocess.Popen(
            ["/usr/bin/python3", str(ROOT / "tests/matching_fixture.py"), str(OUT)]
        )
        processes.append(fixture)
        async with stdio_client(
            StdioServerParameters(
                command=sys.executable, args=["-m", "luda.server"], env=dict(os.environ)
            )
        ) as streams:
            async with ClientSession(*streams) as client:
                await client.initialize()

                async def call(name, **args):
                    response = await client.call_tool(name, args)
                    value = json.loads(response.content[0].text)
                    assert not response.isError, (name, value)
                    return value

                async def refuse(code, **args):
                    response = await client.call_tool("desktop_match_image", args)
                    assert (
                        response.isError
                        and json.loads(response.content[0].text)["code"] == code
                    ), response

                for _ in range(80):
                    windows = await call("desktop_windows")
                    target = next(
                        (w for w in windows["windows"] if w["pid"] == fixture.pid), None
                    )
                    if target and (OUT / "oracle.json").exists():
                        break
                    await asyncio.sleep(0.05)
                assert target
                await call("desktop_activate", window_id=target["window_id"])
                await asyncio.sleep(0.15)
                first = await call("desktop_observe", max_width=2560)
                oracle = json.loads((OUT / "oracle.json").read_text())
                assert first["image_size"]["width"] == first["desktop_size"]["width"]
                bounds = oracle["boxes"][0]
                (OUT / "change").touch()
                for _ in range(80):
                    oracle = json.loads((OUT / "oracle.json").read_text())
                    if oracle["phase"] == 1:
                        break
                    await asyncio.sleep(0.02)
                second = await call("desktop_observe", max_width=2560)
                args = {
                    "template_snapshot_id": first["snapshot_id"],
                    "template_bounds": bounds,
                    "snapshot_id": second["snapshot_id"],
                    "threshold": 0.999,
                }
                result = await call("desktop_match_image", **args)
                assert result["effect"] == "none" and not result["truncated"], result
                assert (
                    sorted(result["candidates"], key=lambda c: c["image_bounds"]["x"])
                    == [
                        {"image_bounds": b, "score": c["score"]}
                        for b, c in zip(
                            oracle["boxes"],
                            sorted(
                                result["candidates"],
                                key=lambda c: c["image_bounds"]["x"],
                            ),
                        )
                    ]
                    and len(result["candidates"]) == 2
                ), (result, oracle)
                results.append(
                    {
                        "case": "two-independent-exact-rendered-icon-boxes",
                        "passed": True,
                        "result": result,
                        "oracle": oracle,
                    }
                )
                limited = await call("desktop_match_image", **args, limit=1)
                assert len(limited["candidates"]) == 1 and limited["truncated"]
                results.append({"case": "bounded-duplicate-truncation", "passed": True})
                await refuse(
                    "MATCH_FLAT_TEMPLATE", **dict(args, template_bounds=oracle["flat"])
                )
                small = await call("desktop_observe", max_width=600)
                await refuse(
                    "MATCH_SCALE_MISMATCH",
                    **dict(args, snapshot_id=small["snapshot_id"]),
                )
                results.append(
                    {"case": "flat-and-scale-mismatch-refused", "passed": True}
                )
                await call(
                    "desktop_window",
                    window_id=target["window_id"],
                    action="move",
                    x=100,
                    y=100,
                )
                for _ in range(80):
                    moved_oracle = json.loads((OUT / "oracle.json").read_text())
                    if moved_oracle["boxes"] != oracle["boxes"]:
                        break
                    await asyncio.sleep(0.02)
                assert moved_oracle["boxes"] != oracle["boxes"]
                moved = await call("desktop_observe", max_width=2560)
                moved_oracle = json.loads((OUT / "oracle.json").read_text())
                moved_result = await call(
                    "desktop_match_image",
                    **dict(args, snapshot_id=moved["snapshot_id"]),
                )
                assert len(moved_result["candidates"]) == 2
                expected = sorted(moved_oracle["boxes"], key=lambda b: b["x"])
                assert (
                    sorted(
                        [c["image_bounds"] for c in moved_result["candidates"]],
                        key=lambda b: b["x"],
                    )
                    == expected
                ), (moved_result, moved_oracle)
                results.append(
                    {
                        "case": "historical-source-window-moved-new-target-exact-boxes",
                        "passed": True,
                    }
                )
                args["snapshot_id"] = moved["snapshot_id"]
                (OUT / "blank").touch()
                for _ in range(80):
                    if json.loads((OUT / "oracle.json").read_text())["phase"] == 2:
                        break
                    await asyncio.sleep(0.02)
                historical = await call("desktop_match_image", **args)
                assert len(historical["candidates"]) == 2
                blank = await call("desktop_observe", max_width=2560)
                none = await call(
                    "desktop_match_image",
                    **dict(args, snapshot_id=blank["snapshot_id"]),
                )
                assert none["candidates"] == []
                results.append(
                    {
                        "case": "historical-target-retained-current-blank-no-match",
                        "passed": True,
                    }
                )
                await call(
                    "desktop_window",
                    window_id=target["window_id"],
                    action="move",
                    x=150,
                    y=150,
                )
                await refuse("STALE_OBSERVATION", **args)
                results.append({"case": "changed-layout-refuses-match", "passed": True})
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        (OUT / "result.json").write_text(
            json.dumps(
                {
                    "cases": results,
                    "engine": subprocess.check_output(
                        ["/usr/bin/python3", "-c", "import cv2;print(cv2.__version__)"],
                        text=True,
                    ).strip(),
                },
                indent=2,
            )
            + "\n"
        )
    print(json.dumps(results))


asyncio.run(main())
