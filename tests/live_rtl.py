"""DATA-10: public MCP logical text/selection versus actual GTK visual RTL navigation."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from qualification_matrix import private_environment, run_bounded
from qualify import source_fingerprint


async def child(output):
    cases = []
    trace = []
    wm = subprocess.Popen(['xfwm4', '--compositor=off'])
    fixture = None
    try:
        end = time.monotonic() + 5
        while subprocess.run(['wmctrl', '-m'], capture_output=True).returncode:
            assert time.monotonic() < end
            await asyncio.sleep(.05)
        fixture = subprocess.Popen(['/usr/bin/python3', str(ROOT / 'tests/rtl_fixture.py'), str(output)])
        async def oracle(predicate):
            end = time.monotonic() + 4
            while time.monotonic() < end:
                try:
                    state = json.loads((output / 'state.json').read_text())
                    if predicate(state):
                        trace.append(state)
                        return state
                except (FileNotFoundError, json.JSONDecodeError):
                    pass
                await asyncio.sleep(.02)
            raise AssertionError('Independent RTL oracle did not reach expected state')
        async with stdio_client(StdioServerParameters(command=sys.executable, args=['-m', 'luda.server'], env=dict(os.environ))) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()
                async def call(name, **args):
                    response = await session.call_tool(name, args)
                    value = json.loads(response.content[0].text)
                    assert not response.isError, (name, value)
                    return value
                end = time.monotonic() + 6
                while True:
                    owner = next((w for w in (await call('desktop_windows'))['windows'] if w['pid'] == fixture.pid), None)
                    if owner:
                        break
                    assert time.monotonic() < end
                    await asyncio.sleep(.05)
                wid = owner['window_id']
                await call('desktop_activate', window_id=wid)
                nodes = (await call('desktop_inspect', window_id=wid))['nodes']
                eid = next(n['element_id'] for n in nodes if n['name'] == 'Mixed RTL text')
                await call('desktop_focus_element', element_id=eid)
                text = 'مرحبا שלום ABC 123 😀 نهاية'
                result = await call('desktop_type', element_id=eid, mode='replace', text=text)
                assert result['effect'] == 'verified'
                await oracle(lambda s: s['text'] == text and s['direction'] == 'rtl')
                read = await call('desktop_read_text', element_id=eid)
                assert read['text'] == text
                cases.append('mixed-rtl-logical-storage-exact')
                await call('desktop_select', element_id=eid, start_offset=2, end_offset=2)
                initial = await oracle(lambda s: s['position'] == 2)
                await call('desktop_press_keys', window_id=wid, chord='Left')
                left = await oracle(lambda s: s['position'] != initial['position'])
                assert left['text'] == text and left['strong_x'] < initial['strong_x']
                assert left['position'] > initial['position']
                cases.append('visual-left-moves-left-while-logical-offset-increases')
                await call('desktop_press_keys', window_id=wid, chord='Right')
                right = await oracle(lambda s: s['position'] != left['position'])
                assert right['strong_x'] > left['strong_x'] and right['position'] == initial['position']
                assert right['text'] == text
                cases.append('visual-right-restores-position-without-text-change')
                start = text.index('😀')
                await call('desktop_select', element_id=eid, start_offset=start, end_offset=start + 1)
                await oracle(lambda s: list(s['selection']) == [start, start + 1])
                replacement = 'שָׁלוֹם42'
                expected = text[:start] + replacement + text[start + 1:]
                result = await call('desktop_type', element_id=eid, mode='insert', text=replacement)
                assert result['effect'] == 'verified'
                await oracle(lambda s: s['text'] == expected)
                assert (await call('desktop_read_text', element_id=eid))['text'] == expected
                cases.append('logical-emoji-selection-and-combining-hebrew-replacement-exact')
    finally:
        for process in (fixture, wm):
            if process and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
        (output / 'results.json').write_text(json.dumps({'passed_cases': cases, 'oracle_trace': trace}, indent=2))


def main():
    if os.geteuid() == 0:
        raise SystemExit('Run as ordinary desktop account')
    if len(sys.argv) == 3 and sys.argv[1] == '--child':
        return asyncio.run(child(Path(sys.argv[2])))
    output = ROOT / 'artifacts/rtl' / str(time.time_ns())
    output.mkdir(parents=True)
    before = source_fingerprint(ROOT)
    with tempfile.TemporaryDirectory(prefix='luda-rtl-session-') as directory:
        token = uuid.uuid4().hex
        env = private_environment(Path(directory), token)
        with (output / 'desktop.log').open('wb') as log:
            result = run_bounded(['xvfb-run', '-a', '-s', '-screen 0 1440x1000x24 -nolisten tcp',
                                  'dbus-run-session', '--', sys.executable, __file__, '--child', str(output)], env, log, 60, token)
    after = source_fingerprint(ROOT)
    result.update(source=before, source_after=after, source_unchanged=before == after)
    (output / 'runner.json').write_text(json.dumps(result, indent=2))
    print(output, result['status'])
    return 0 if result['status'] == 'passed' and before == after else 1


if __name__ == '__main__':
    raise SystemExit(main())
