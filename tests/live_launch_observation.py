"""Public MCP launch observations; run only via the isolated headless runner."""
import asyncio
import ctypes
import json
import os
from pathlib import Path
import signal
import sys
import tempfile
import time
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client

FIXTURE='''import gi,json,os,sys
from pathlib import Path
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,GLib
output=Path(sys.argv[1]);mode=sys.argv[2];windows=[]
with output.with_suffix('.starts').open('a') as log:log.write(str(os.getpid())+'\\n')
proof={'pid':os.getpid(),'start':Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19],'starts':1,'windows':[]}
def save():output.write_text(json.dumps(proof))
def window(title):
 w=Gtk.Window(title=title);w.add(Gtk.Label(label=title));w.show_all();windows.append(w)
 proof['windows'].append({'xid':w.get_window().get_xid(),'title':title});save();return False
save()
if mode=='two':window('Early unrelated splash');GLib.timeout_add(250,window,'Requested document')
else:GLib.timeout_add(500,window,'Delayed document')
Gtk.main()
'''

async def main():
    assert os.getuid()!=0 and os.environ.get('LUDA_ISOLATED_TEST_DISPLAY')=='1'
    # Reap only our app descendants after their short-lived Gio helper exits.
    assert ctypes.CDLL(None).prctl(36,1,0,0,0)==0
    owned=[];checks=[]
    with tempfile.TemporaryDirectory(prefix='luda-launch-observation-') as directory:
        base=Path(directory);entries=base/'applications';entries.mkdir();script=base/'fixture.py';script.write_text(FIXTURE)
        for mode in ('two','delayed','zero'):
            (entries/f'luda-{mode}.desktop').write_text(f'[Desktop Entry]\nType=Application\nName=Luda {mode}\nExec=/usr/bin/python3 "{script}" "{base/mode}" {mode}\nTerminal=false\n')
        params=StdioServerParameters(command=sys.executable,args=['-m','luda.server'],env={**os.environ,'XDG_DATA_HOME':str(base)})
        async def proof(mode):
            deadline=time.monotonic()+3
            while time.monotonic()<deadline:
                try:return json.loads((base/mode).read_text())
                except (FileNotFoundError,json.JSONDecodeError):await asyncio.sleep(.02)
            raise AssertionError('Owned application did not publish its oracle')
        try:
            async with stdio_client(params) as streams:
                async with ClientSession(*streams) as session:
                    await session.initialize()
                    async def call(name,**args):
                        result=await session.call_tool(name,args);payload=json.loads(result.content[0].text)
                        assert not result.isError,payload
                        return payload
                    tools={t.name:t for t in (await session.list_tools()).tools}
                    assert tools['desktop_launch'].inputSchema['properties']['wait_timeout']['default']==1
                    for mode,wait in [('two',1),('delayed',.1),('zero',0)]:
                        result=await call('desktop_launch',application_id=f'luda-{mode}.desktop',wait_timeout=wait)
                        state=result['window_observation'];oracle=await proof(mode);owned.append(oracle['pid'])
                        assert result['spawned_processes']==[{'pid':oracle['pid'],'start':oracle['start']}],result
                        assert result['effect']=='dispatched'
                        if mode=='two':
                            assert state['state']=='multiple_candidates' and state['total_candidates']==2,state
                            assert {w['title'] for w in state['candidates']}=={w['title'] for w in oracle['windows']},(state,oracle)
                            assert all(w['pid']==oracle['pid'] and w['start']==oracle['start'] for w in state['candidates'])
                            checks.append('two same-generation windows, early decoy not called ready')
                        else:
                            assert state['state']==('pending' if mode=='delayed' else 'not_requested'),state
                            checks.append(mode+' single dispatch')
                    await asyncio.sleep(.65)
                    for mode in ('two','delayed','zero'):
                        oracle=await proof(mode);assert (base/mode).with_suffix('.starts').read_text().splitlines()==[str(oracle['pid'])];assert oracle['starts']==1 and len(oracle['windows'])==(2 if mode=='two' else 1),oracle
                    invalid=await session.call_tool('desktop_launch',{'application_id':'luda-two.desktop','wait_timeout':True})
                    assert invalid.isError
                    checks.append('raw boolean wait refused')
            # The exited launch helpers leave no unreaped owned child here.
        finally:
            for mode in ('two','delayed','zero'):
                try:
                    pid=json.loads((base/mode).read_text())['pid']
                    if pid not in owned:owned.append(pid)
                except (FileNotFoundError,json.JSONDecodeError):pass
            for pid in owned:
                try:os.kill(pid,signal.SIGTERM)
                except ProcessLookupError:pass
            deadline=time.monotonic()+3
            pending=set(owned)
            while pending and time.monotonic()<deadline:
                for pid in list(pending):
                    try:
                        if os.waitpid(pid,os.WNOHANG)[0]:pending.remove(pid)
                    except ChildProcessError:
                        if not Path(f'/proc/{pid}').exists():pending.remove(pid)
                await asyncio.sleep(.02)
            assert not pending,('Unreaped owned applications',pending)
        checks.append('owned apps terminated and reaped; no replay')
    print(json.dumps({'checks':checks,'uid':os.getuid(),'scope':'process-bound candidates, not request-document readiness'}))

asyncio.run(main())
