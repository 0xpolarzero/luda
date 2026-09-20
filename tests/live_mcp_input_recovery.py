"""Public MCP recovery after real owned guardian/X-server interruption."""
import asyncio
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import tempfile
import time
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from live_keyboard_guard import Oracle, descendants
from luda.common import stop_process

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/mcp-input-recovery'

async def until(predicate,timeout=10):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        result=predicate()
        if result:return result
        await asyncio.sleep(.002)
    raise AssertionError('Owned-process/oracle deadline exceeded')

async def main():
    if os.getuid()==0 or os.environ.get('LUDA_ISOLATED_TEST_DISPLAY')!='1':
        raise SystemExit('Run as ordinary user under the isolated qualification runner')
    OUT.mkdir(parents=True,exist_ok=True)
    results=[];xserver=None;wm=None;fixture=None;oracle=None;stopped={}
    def record(case,okay,**details):
        results.append({'case':case,'passed':bool(okay),**details})
        assert okay,results[-1]
    async def call(session,name,allow_error=False,**arguments):
        response=await asyncio.wait_for(session.call_tool(name,arguments),15)
        try:value=json.loads(response.content[0].text)
        except json.JSONDecodeError:raise AssertionError((name,response))
        if not allow_error:assert not response.isError,(name,value)
        return value
    with tempfile.TemporaryDirectory(prefix='luda-mcp-recovery-') as directory:
        base=Path(directory);authority=base/'authority';authority.touch(mode=0o600)
        reader,writer=os.pipe()
        xserver=subprocess.Popen(['Xvfb','-displayfd',str(writer),'-screen','0','900x700x24','-nolisten','tcp','-ac','-auth',str(authority)],pass_fds=(writer,),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        os.close(writer)
        assert select.select([reader],[],[],5)[0]
        display=':'+os.read(reader,32).decode().strip();os.close(reader)
        oldenv=dict(os.environ);os.environ.update(DISPLAY=display,XAUTHORITY=str(authority));env=dict(os.environ)
        def command(*argv):return subprocess.run(argv,env=env,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=3)
        try:
            wm=subprocess.Popen(['xfwm4','--compositor=off'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            await until(lambda:subprocess.run(['wmctrl','-m'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=2).returncode==0)
            fixture=subprocess.Popen(['/usr/bin/python3',str(ROOT/'tests/keyboard_fixture.py'),directory],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            oracle=Oracle();pidfile=base/'mcp.pid'
            code="import os,sys;from pathlib import Path;Path(sys.argv.pop()).write_text(str(os.getpid()));from luda.server import main;main()"
            params=StdioServerParameters(command=sys.executable,args=['-c',code,str(pidfile)],env=env)
            async with stdio_client(params) as streams:
                async with ClientSession(*streams) as session:
                    await session.initialize();server_pid=int(pidfile.read_text())
                    tools=await session.list_tools()
                    record('public-recovery-tool-discoverable',any(t.name=='desktop_recover_input' for t in tools.tools))
                    deadline=time.monotonic()+8
                    while True:
                        windows=await call(session,'desktop_windows')
                        window=next((w for w in windows['windows'] if w['pid']==fixture.pid),None)
                        if window:break
                        assert time.monotonic()<deadline
                        await asyncio.sleep(.05)
                    await call(session,'desktop_activate',window_id=window['window_id'])
                    async def interrupt(label):
                        key=asyncio.create_task(call(session,'desktop_press_keys',allow_error=True,window_id=window['window_id'],chord='ctrl+shift+alt+F12'))
                        await until(lambda:oracle.code('Control_L') in oracle.pressed())
                        guards=[pid for pid in descendants(server_pid) if b'luda._keyboard_guard' in Path('/proc',str(pid),'cmdline').read_bytes()]
                        assert len(guards)==1,guards
                        children=descendants(guards[0]);assert len(children)==1,children
                        os.kill(children[0],signal.SIGSTOP);stopped[children[0]]=Path('/proc',str(children[0]),'stat').read_text().rsplit(')',1)[1].split()[19]
                        os.kill(guards[0],signal.SIGSTOP);stopped[guards[0]]=Path('/proc',str(guards[0]),'stat').read_text().rsplit(')',1)[1].split()[19]
                        os.kill(xserver.pid,signal.SIGSTOP);stopped[xserver.pid]=Path('/proc',str(xserver.pid),'stat').read_text().rsplit(')',1)[1].split()[19]
                        paused=await call(session,'desktop_control',action='pause')
                        assert paused['paused']
                        outcome=await key
                        record(label+'-interrupted-key-outcome-uncertain',not outcome['ok'] and outcome['effect']=='uncertain',outcome=outcome)
                        # The real watcher resumes the stopped guardian, which
                        # kills its injector; blocked X makes its release fail.
                        await until(lambda:not Path('/proc',str(guards[0])).exists(),8)
                        status=await call(session,'desktop_status')
                        record(label+'-failed-native-cleanup-keeps-quarantine',status['recovering'])
                        blocked=await call(session,'desktop_press_keys',allow_error=True,window_id=window['window_id'],chord='a')
                        record(label+'-quarantine-refuses-new-input',blocked.get('code')=='BUSY',outcome=blocked)
                    await interrupt('original')
                    pending=await call(session,'desktop_recover_input')
                    record('unavailable-original-server-stays-pending',pending['pending_count']==1 and pending['recovering'],outcome=pending)
                    os.kill(xserver.pid,signal.SIGCONT)
                    recovery=await call(session,'desktop_recover_input')
                    record('public-recovery-releases-owned-input',recovery['pending_count']==0 and not recovery['recovering'],outcome=recovery)
                    record('independent-key-state-clean',not oracle.pressed())
                    pause=await call(session,'desktop_control')
                    refused=await call(session,'desktop_press_keys',allow_error=True,window_id=window['window_id'],chord='a')
                    record('recovery-preserves-pause',pause['paused'] and refused.get('code')=='CONTROL_PAUSED',outcome=refused)
                    await call(session,'desktop_control',action='resume')
                    await call(session,'desktop_press_keys',window_id=window['window_id'],chord='a')
                    await until(lambda:json.loads((base/'state.json').read_text())['text']=='a')
                    record('explicit-resume-restores-input',True)
                    await interrupt('replacement')
                    # Replace only our server, at the same address/auth path.
                    os.kill(xserver.pid,signal.SIGCONT);oracle.close();oracle=None
                    stop_process(xserver)
                    xserver=subprocess.Popen(['Xvfb',display,'-screen','0','900x700x24','-nolisten','tcp','-ac','-auth',str(authority)],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                    await until(lambda:subprocess.run(['xdpyinfo'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=2).returncode==0)
                    oracle=Oracle();command('xdotool','keydown','Control_L');command('xdotool','mousedown','1')
                    held=oracle.pressed();buttons=oracle.buttons()
                    replaced=await call(session,'desktop_recover_input')
                    record('replacement-server-proof-clears-only-quarantine',replaced['pending_count']==0 and any(r.get('proof')=='original_server_replaced' for r in replaced['recoveries']),outcome=replaced)
                    record('replacement-held-key-and-button-untouched',bool(held) and bool(buttons) and oracle.pressed()==held and oracle.buttons()==buttons)
                    record('replacement-recovery-preserves-pause',(await call(session,'desktop_control'))['paused'])
                    command('xdotool','keyup','Control_L');command('xdotool','mouseup','1')
        finally:
            for pid,start in stopped.items():
                try:
                    if Path('/proc',str(pid),'stat').read_text().rsplit(')',1)[1].split()[19]==start:
                        os.kill(pid,signal.SIGCONT)
                except (ProcessLookupError,FileNotFoundError):pass
            if oracle:oracle.close()
            for child in (fixture,wm,xserver):
                if child:stop_process(child)
            os.environ.clear();os.environ.update(oldenv)
            (OUT/'results.json').write_text(json.dumps(results,indent=2)+'\n')
            print(json.dumps({'cases':len(results),'passed':sum(r['passed'] for r in results)}))

if __name__=='__main__':asyncio.run(main())
