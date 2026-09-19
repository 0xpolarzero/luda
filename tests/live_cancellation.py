"""Cancel a real MCP request against a stopped owned provider, then inspect late effects."""
import argparse
import asyncio
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

from mcp import ClientSession, StdioServerParameters, types
from mcp.shared.exceptions import McpError
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts/cancellation'


async def main(server):
    OUT.mkdir(parents=True, exist_ok=True)
    fixture = subprocess.Popen(['/usr/bin/python3', str(ROOT / 'tests/fixture.py'), str(OUT)])
    results = []
    def record(name, passed, **details):
        results.append({'case': name, 'passed': bool(passed), **details})
        assert passed, results[-1]
    async def call(session, name, **arguments):
        response = await session.call_tool(name, arguments)
        data = json.loads(response.content[0].text)
        assert not response.isError, (name, data)
        return data
    try:
        async with stdio_client(StdioServerParameters(command=server, env=dict(os.environ))) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()
                deadline = time.monotonic() + 5
                while True:
                    windows = await call(session, 'desktop_windows')
                    window = next((w for w in windows['windows'] if w['pid'] == fixture.pid), None)
                    if window:
                        break
                    assert time.monotonic() < deadline, 'Fixture failed to map'
                    await asyncio.sleep(.05)
                await call(session, 'desktop_activate', window_id=window['window_id'])
                tree = await call(session, 'desktop_inspect', window_id=window['window_id'])
                element = next(n for n in tree['nodes'] if n['name'] == 'Contract text')
                sentinel = 'before cancellation\n'
                await call(session, 'desktop_set_text', element_id=element['element_id'], text=sentinel)
                await asyncio.sleep(.15)
                os.kill(fixture.pid, signal.SIGSTOP)
                began = time.monotonic()
                # The pinned SDK does not send protocol cancellation when a
                # local asyncio waiter is cancelled. Send the real MCP message.
                # Capture the next ID with no other request pending in this
                # test; this private SDK detail is isolated to the harness.
                request_id = session._request_id
                pending = asyncio.create_task(session.call_tool('desktop_set_text', {
                    'element_id': element['element_id'], 'text': 'must not arrive after cancellation\n'}))
                await asyncio.sleep(.15)
                await session.send_notification(types.ClientNotification(types.CancelledNotification(
                    params=types.CancelledNotificationParams(requestId=request_id, reason='qualification test'))))
                try:
                    response = await asyncio.wait_for(pending, timeout=2)
                except McpError as exc:
                    record('client-cancellation-delivered', 'cancel' in str(exc).lower(), seconds=round(time.monotonic()-began, 3))
                else:
                    record('client-cancellation-delivered', response.isError, seconds=round(time.monotonic()-began, 3))
                # This tool has no GUI dependency and must remain responsive
                # while the cancelled worker is being cleaned up.
                status = await asyncio.wait_for(call(session, 'desktop_status'), timeout=2)
                record('status-responsive-after-cancel', status['ok'], status=status)
                deadline = time.monotonic() + 2
                while status.get('recovering') or not any(op.get('code') == 'CANCELLED' for op in status['operations']):
                    assert time.monotonic() < deadline, ('Cancellation cleanup did not finish', status)
                    await asyncio.sleep(.02)
                    status = await call(session, 'desktop_status')
                record('cancelled-worker-cleanup-acknowledged', True, status=status)
                os.kill(fixture.pid, signal.SIGCONT)
                await asyncio.sleep(.6)
                value = json.loads((OUT / 'state.json').read_text())['text']
                record('cancelled-write-has-no-late-effect', value == sentinel)
                deadline = time.monotonic() + 3
                while True:
                    response = await session.call_tool('desktop_inspect', {'window_id': window['window_id']})
                    if not response.isError:
                        break
                    assert time.monotonic() < deadline, response
                    await asyncio.sleep(.05)
                record('inspection-recovers-after-cancel', True)
    finally:
        if fixture.poll() is None:
            os.kill(fixture.pid, signal.SIGCONT)
            fixture.terminate()
            fixture.wait(timeout=3)
        (OUT / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
        print(json.dumps(results, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--server', default=str(Path(sys.executable).parent / 'luda'))
    asyncio.run(main(parser.parse_args().server))
