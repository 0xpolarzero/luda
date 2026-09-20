"""Nested GTK pane wheel targeting through actual MCP and adjustment oracles."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]

async def main():
    if os.getuid() == 0 or os.environ.get('LUDA_ISOLATED_TEST_DISPLAY') != '1':
        raise RuntimeError('Use an ordinary user and an isolated display.')
    records = []
    with tempfile.TemporaryDirectory(prefix='luda-nested-scroll-') as directory:
        state = Path(directory) / 'state.json'
        app = subprocess.Popen(['/usr/bin/python3', str(ROOT/'tests/nested_scroll_fixture.py'), str(state)])
        try:
            async with stdio_client(StdioServerParameters(command=str(ROOT/'.venv/bin/luda'), env=dict(os.environ))) as streams:
                async with ClientSession(*streams) as session:
                    await session.initialize()
                    async def call(name, **arguments):
                        result = await session.call_tool(name, arguments)
                        value = json.loads(result.content[0].text)
                        assert not result.isError, (name, value)
                        return value
                    async def wait(predicate):
                        end = time.monotonic()+4
                        while time.monotonic()<end:
                            value = await predicate()
                            if value: return value
                            await asyncio.sleep(.03)
                        raise AssertionError('Nested pane oracle timed out')
                    async def find_window():
                        return next((w for w in (await call('desktop_windows'))['windows'] if w['pid']==app.pid), None)
                    window = await wait(find_window)
                    wid = window['window_id']
                    await call('desktop_activate', window_id=wid)
                    def oracle(): return json.loads(state.read_text())
                    async def pane(name):
                        async def find():
                            return next((n for n in (await call('desktop_inspect',window_id=wid))['nodes'] if n['name']==name),None)
                        return await wait(find)
                    async def scroll(name, direction, expected, x_fraction=.5):
                        target = await pane(name)
                        before = oracle()
                        shot = await call('desktop_observe')
                        b = target['bounds']; image=shot['image_size']; native=shot['desktop_size']
                        result = await call('desktop_scroll',window_id=wid,snapshot_id=shot['snapshot_id'],
                            x=(b['x']+b['width']*x_fraction)*image['width']/native['width'],
                            y=(b['y']+b['height']*.35)*image['height']/native['height'],direction=direction,ticks=3)
                        async def changed(): return oracle()[expected]['value'] != before[expected]['value']
                        await wait(changed)
                        # Observe a bounded quiet period; do not retry delivered input.
                        await asyncio.sleep(.25)
                        after=oracle()
                        moved=[key for key in before if before[key]['value'] != after[key]['value']]
                        assert moved == [expected], (name,direction,before,after)
                        assert result['effect']=='dispatched', result
                        records.append(dict(pane=name,direction=direction,moved=moved,before=before,after=after))
                    await scroll('Inner scrolling pane','down','inner_y')
                    await scroll('Inner scrolling pane','right','inner_x')
                    await scroll('Outer scrolling pane','down','outer_y',x_fraction=.9)
        finally:
            app.terminate()
            app.wait(timeout=3)
    out=ROOT/'artifacts/nested-scroll';out.mkdir(parents=True,exist_ok=True)
    evidence=dict(uid=os.getuid(),passed=records)
    (out/'results.json').write_text(json.dumps(evidence,indent=2)+'\n')
    print(json.dumps(evidence))

if __name__=='__main__':asyncio.run(main())
