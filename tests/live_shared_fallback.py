"""Real MCP fallback into a core-only app with independent application readback."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from live_keyboard_guard import wait
ROOT=Path(__file__).resolve().parents[1]

async def child():
    children=[]
    def launch(*args):
        p=subprocess.Popen(args,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);children.append(p);return p
    def command(*args):return subprocess.check_output(args,text=True,timeout=3).strip()
    try:
        with tempfile.TemporaryDirectory(prefix='luda-core-fallback-') as directory:
            base=Path(directory);binary=base/'core-app';out=base/'state.json'
            subprocess.run(['gcc','-Wall','-Wextra',str(ROOT/'tests/core_input_fixture.c'),'-lX11','-o',str(binary)],check=True)
            launch('xfwm4','--compositor=off')
            wait(lambda:subprocess.run(['wmctrl','-m'],capture_output=True).returncode==0)
            app=launch(str(binary),str(out))
            human=launch('/usr/bin/python3',str(ROOT/'tests/private_input_fixture.py'),str(base/'human.json'),'Luda fallback human')
            wait(lambda:out.exists() and (base/'human.json').exists())
            human_xid=command('xdotool','search','--name','^Luda fallback human$')
            command('xdotool','windowmove',human_xid,'700','80')
            command('xdotool','windowactivate','--sync',human_xid)
            command('xdotool','mousemove','1200','700')
            def state():return json.loads(out.read_text())
            params=StdioServerParameters(command=str(ROOT/'.venv/bin/luda'),env=dict(os.environ))
            async with stdio_client(params) as streams:
                async with ClientSession(*streams) as client:
                    await client.initialize()
                    async def call(name,**args):
                        result=await client.call_tool(name,args);value=json.loads(result.content[0].text)
                        assert not result.isError,(name,value)
                        return value
                    windows=(await call('desktop_windows'))['windows']
                    target=next(w for w in windows if w['pid']==app.pid);wid=target['window_id']
                    shot=await call('desktop_observe',max_width=2560)
                    bounds=target['bounds'];x,y=bounds['x']+80,bounds['y']+80
                    await call('desktop_click',window_id=wid,snapshot_id=shot['snapshot_id'],x=x,y=y)
                    wait(lambda:state()['clicks']==1 and state()['releases']==1)
                    assert int(command('xdotool','getactivewindow'))==target['xid']
                    command('xdotool','windowactivate','--sync',human_xid)
                    await call('desktop_press_keys',window_id=wid,chord='a',count=3)
                    wait(lambda:state()['text']=='aaa')
                    assert int(command('xdotool','getactivewindow'))==target['xid']
                    assert json.loads((base/'human.json').read_text())['text']==''
                    report={'passed':True,'checks':['unknown toolkit gets automatic shared pointer fallback','core-only app click effect exactly once','automatic shared keyboard activation','three exact characters in intended app','human app did not receive fallback keys'],'scope':'real MCP on private Xvfb/XFWM, independent core-only application file oracle'}
                    output=ROOT/'artifacts/shared-fallback';output.mkdir(parents=True,exist_ok=True)
                    (output/'results.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
    finally:
        for p in reversed(children):
            if p.poll() is None:
                p.terminate()
                try:p.wait(timeout=3)
                except subprocess.TimeoutExpired:p.kill();p.wait(timeout=3)

def main():
    if '--child' in sys.argv:
        assert os.environ.get('LUDA_PRIVATE_TEST')=='1' and os.environ.get('DISPLAY')!=':1'
        return asyncio.run(child())
    with tempfile.TemporaryDirectory(prefix='luda-fallback-session-') as directory:
        env=dict(os.environ,LUDA_PRIVATE_TEST='1',GSETTINGS_BACKEND='memory',NO_AT_BRIDGE='0')
        for key in ('XDG_CONFIG_HOME','XDG_DATA_HOME','XDG_CACHE_HOME','XDG_RUNTIME_DIR'):
            path=Path(directory)/key;path.mkdir(mode=0o700);env[key]=str(path)
        result=subprocess.run(['xvfb-run','-a','-s','-screen 0 1400x900x24 -nolisten tcp','dbus-run-session','--',sys.executable,__file__,'--child'],env=env,timeout=90)
        raise SystemExit(result.returncode)
if __name__=='__main__':main()
