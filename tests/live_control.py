"""Shared pause contract through two independent real stdio MCP servers."""
import asyncio
from contextlib import AsyncExitStack
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/control'

async def main():
    if os.environ.get('LUDA_ISOLATED_TEST_DISPLAY')!='1':
        raise SystemExit('Run this control-state test only on an isolated test display.')
    OUT.mkdir(parents=True,exist_ok=True)
    fixture=subprocess.Popen(['/usr/bin/python3',str(ROOT/'tests/fixture.py'),str(OUT)])
    results=[]
    def record(name,passed):
        results.append({'case':name,'passed':bool(passed)})
        assert passed,name
    async def call(session,tool_name,**args):
        result=await session.call_tool(tool_name,args)
        return result,json.loads(result.content[0].text)
    try:
        async with AsyncExitStack() as stack:
            sessions=[]
            for _ in range(2):
                transport=await stack.enter_async_context(stdio_client(StdioServerParameters(command=str(Path(sys.executable).parent/'luda'),env=dict(os.environ))))
                client=await stack.enter_async_context(ClientSession(*transport));await client.initialize();sessions.append(client)
            a,b=sessions
            try:
                await call(a,'desktop_control',action='resume')
                deadline=time.monotonic()+5
                while True:
                    _,data=await call(a,'desktop_windows')
                    window=next((w for w in data['windows'] if w['pid']==fixture.pid),None)
                    if window:break
                    assert time.monotonic()<deadline
                    await asyncio.sleep(.05)
                await call(a,'desktop_activate',window_id=window['window_id'])
                _,data=await call(a,'desktop_inspect',window_id=window['window_id'],name='Contract text')
                element=data['nodes'][0]['element_id']
                result,_=await call(a,'desktop_type',element_id=element,text='preserve me',mode='replace')
                assert not result.isError
                await call(b,'desktop_control',action='pause')
                result,data=await call(a,'desktop_type',element_id=element,text='must not write',mode='replace')
                record('peer-pause-prevents-input',result.isError and data['code']=='CONTROL_PAUSED' and data['effect']=='none')
                result,_=await call(a,'desktop_observe',max_width=640)
                record('observation-available-while-paused',not result.isError)
                await asyncio.sleep(.1)
                record('paused-input-independent-readback',json.loads((OUT/'state.json').read_text())['text']=='preserve me')
                await call(b,'desktop_control',action='resume')
                result,_=await call(a,'desktop_type',element_id=element,text='resumed',mode='replace')
                await asyncio.sleep(.1)
                record('peer-resume-restores-input',not result.isError and json.loads((OUT/'state.json').read_text())['text']=='resumed')
            finally:
                await call(b,'desktop_control',action='resume')
    finally:
        fixture.terminate();fixture.wait(timeout=3)
        (OUT/'results.json').write_text(json.dumps(results,indent=2))
        print(json.dumps(results))

if __name__=='__main__':asyncio.run(main())
