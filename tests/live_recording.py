"""Actual MCP recording start/stop, decoded frames, pause cleanup and retention."""

import asyncio, json, os, subprocess, sys, time
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts/recording" / str(time.time_ns())
OUT.mkdir(parents=True)
assert os.getuid() != 0 and os.environ.get("LUDA_ISOLATED_TEST_DISPLAY") == "1"


async def main():
    processes = []
    records = []
    saved = None
    try:
        wm = subprocess.Popen(
            ["xfwm4", "--compositor=off"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        processes.append(wm)
        for _ in range(100):
            if subprocess.run(["wmctrl", "-m"], capture_output=True).returncode == 0:
                break
            await asyncio.sleep(0.05)
        app = subprocess.Popen(
            ["/usr/bin/python3", str(ROOT / "tests/recording_fixture.py"), str(OUT)]
        )
        processes.append(app)
        async with stdio_client(
            StdioServerParameters(
                command=sys.executable, args=["-m", "luda.server"], env=dict(os.environ)
            )
        ) as streams:
            async with ClientSession(*streams) as client:
                await client.initialize()

                async def call(name, **arguments):
                    value = await client.call_tool(name, arguments)
                    result = json.loads(value.content[0].text)
                    assert not value.isError, (name, result)
                    return result

                for _ in range(100):
                    if (OUT / "state.json").exists():
                        break
                    await asyncio.sleep(0.05)
                value = await call("desktop_recording", action="start", max_seconds=10)
                assert value["state"] == "recording" and "path" not in value
                ticket = value["recording_id"]
                await asyncio.sleep(0.3)
                (OUT / "green").touch()
                await asyncio.sleep(0.5)
                await call("desktop_control", action="pause")
                value = await call(
                    "desktop_recording", action="stop", recording_id=ticket
                )
                assert value["state"] == "complete" and value["playable_verified"], (
                    value
                )
                saved = Path(value["path"])
                assert saved.is_file() and saved.stat().st_mode & 0o077 == 0
                frames = subprocess.run(
                    [
                        "ffmpeg",
                        "-v",
                        "error",
                        "-i",
                        str(saved),
                        "-vf",
                        "scale=1:1",
                        "-f",
                        "rawvideo",
                        "-pix_fmt",
                        "rgb24",
                        "-",
                    ],
                    capture_output=True,
                    check=True,
                    timeout=10,
                ).stdout
                pixels = [tuple(frames[i : i + 3]) for i in range(0, len(frames), 3)]
                assert any(r > g + 15 for r, g, b in pixels) and any(
                    g > r + 15 for r, g, b in pixels
                ), pixels
                records.append(
                    {
                        "case": "start-stop-playable-red-and-green-frames",
                        "passed": True,
                        "frames": len(pixels),
                        "bytes": value["bytes"],
                    }
                )
                foreign = saved.parent / "user-note"
                foreign.write_text("preserve this user-owned addition")
                value = await call(
                    "desktop_recording", action="delete", recording_id=ticket
                )
                assert (
                    value["state"] == "deleted"
                    and not saved.exists()
                    and foreign.read_text() == "preserve this user-owned addition"
                )
                records.append(
                    {
                        "case": "paused-stop-delete-preserves-user-added-file",
                        "passed": True,
                    }
                )
                foreign.unlink()
                foreign.parent.rmdir()
                await call("desktop_control", action="resume")
                value = await call("desktop_recording", action="start", max_seconds=1)
                ticket = value["recording_id"]
                for _ in range(150):
                    value = await call(
                        "desktop_recording", action="status", recording_id=ticket
                    )
                    if value["state"] in ("complete", "failed"):
                        break
                    await asyncio.sleep(0.05)
                assert value["state"] == "complete", value
                saved = Path(value["path"])
                records.append(
                    {
                        "case": "automatic-duration-completes-playable-file",
                        "passed": True,
                    }
                )
        for _ in range(100):
            if not saved.exists():
                break
            await asyncio.sleep(0.05)
        assert not saved.exists()
        records.append(
            {
                "case": "connection-close-deletes-completed-temporary-artifact",
                "passed": True,
            }
        )
    finally:
        for process in reversed(processes):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        (OUT / "result.json").write_text(json.dumps(records, indent=2) + "\n")
    print(json.dumps(records))


asyncio.run(main())
