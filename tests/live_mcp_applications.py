"""Actual MCP application discovery/launch with an independent GTK oracle."""
import asyncio
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client

async def main():
    with tempfile.TemporaryDirectory() as directory:
        base=Path(directory);entries=base/'applications';entries.mkdir();output=base/'proof.json';script=base/'fixture.py'
        script.write_text('import gi,json,os,sys\nfrom pathlib import Path\ngi.require_version("Gtk","3.0")\nfrom gi.repository import Gtk\nw=Gtk.Window(title="Luda MCP launched proof");w.show_all()\nPath(sys.argv[1]).write_text(json.dumps({"pid":os.getpid(),"args":sys.argv[2:]}))\nGtk.main()\n')
        (entries/'luda-mcp-proof.desktop').write_text(f'[Desktop Entry]\nType=Application\nName=Luda MCP launch proof\nExec=/usr/bin/python3 "{script}" "{output}" %F\nTerminal=false\n')
        target=base/'日本語 target.txt';target.write_text('fixture')
        params=StdioServerParameters(command=sys.executable,args=['-m','luda.server'],env={**os.environ,'XDG_DATA_HOME':str(base)})
        pid=None;paused_before=False
        try:
            async with stdio_client(params) as streams:
                async with ClientSession(*streams) as session:
                    await session.initialize()
                    names={tool.name for tool in (await session.list_tools()).tools}
                    assert {'desktop_applications','desktop_launch'}<=names
                    async def call(name,**args):
                        result=await session.call_tool(name,args)
                        return result,json.loads(result.content[0].text)
                    _,control=await call('desktop_control');paused_before=control['paused']
                    try:
                        await call('desktop_control',action='pause')
                        result,found=await call('desktop_applications',query='Luda MCP launch proof')
                        assert not result.isError and found['applications'][0]['application_id']=='luda-mcp-proof.desktop',found
                        result,blocked=await call('desktop_launch',application_id='luda-mcp-proof.desktop')
                        assert result.isError and blocked['code']=='CONTROL_PAUSED' and not output.exists(),blocked
                        await call('desktop_control',action='resume')
                        result,launch=await call('desktop_launch',application_id='luda-mcp-proof.desktop',files_or_uris=[str(target)])
                        assert not result.isError and launch['effect']=='dispatched',launch
                        for _ in range(40):
                            if output.exists():break
                            await asyncio.sleep(.05)
                        proof=json.loads(output.read_text());pid=proof['pid'];assert proof['args']==[str(target)]
                        _,windows=await call('desktop_windows')
                        assert any(w['pid']==pid for w in windows['windows']),windows
                        _,history=await call('desktop_status')
                        assert any(op['method']=='launch_application' and op['effect']=='dispatched' for op in history['operations'])
                        result,bad=await call('desktop_launch',application_id='missing.desktop')
                        assert result.isError and bad['code']=='APPLICATION_NOT_FOUND',bad
                    finally:
                        await call('desktop_control',action='pause' if paused_before else 'resume')
            print(json.dumps({'mcp_tools':'discovered','paused_discovery':'available','paused_launch':'rejected','launch':'dispatched with independent argv and visible window','history':'recorded'}))
        finally:
            if pid:
                try:os.kill(pid,signal.SIGTERM)
                except ProcessLookupError:pass

asyncio.run(main())
