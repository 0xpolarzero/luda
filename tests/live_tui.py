"""TERM-09: real curses alternate screen, public MCP input, independent app state."""
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
    cases=[];trace=[];terminal=None
    wm=subprocess.Popen(['xfwm4','--compositor=off'])
    async def oracle(predicate):
        end=time.monotonic()+5
        while time.monotonic()<end:
            try:
                value=json.loads((output/'state.json').read_text())
                if predicate(value):trace.append(value);return value
            except (FileNotFoundError,json.JSONDecodeError):pass
            await asyncio.sleep(.02)
        raise AssertionError('TUI oracle deadline')
    try:
        end=time.monotonic()+5
        while subprocess.run(['wmctrl','-m'],capture_output=True).returncode:
            assert time.monotonic()<end;await asyncio.sleep(.05)
        terminal=subprocess.Popen(['xterm','-title','Luda owned TUI','-xrm','*VT100.translations: #override Ctrl Shift <Key>V: insert-selection(CLIPBOARD)','-e','/usr/bin/python3',str(ROOT/'tests/tui_fixture.py'),str(output)])
        async with stdio_client(StdioServerParameters(command=sys.executable,args=['-m','luda.server'],env=dict(os.environ))) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()
                async def call(name,**args):
                    response=await session.call_tool(name,args)
                    value=json.loads(next(c.text for c in response.content if c.type=='text'))
                    assert not response.isError,(name,value)
                    return value,response
                end=time.monotonic()+5
                while True:
                    windows,_=await call('desktop_windows')
                    owner=next((w for w in windows['windows'] if w['pid']==terminal.pid),None)
                    if owner:break
                    assert time.monotonic()<end;await asyncio.sleep(.05)
                wid=owner['window_id'];await call('desktop_activate',window_id=wid)
                state=await oracle(lambda v:v['phase']=='tui')
                assert state['mode_before']==2 and state['mode_inside']==1,state
                async def screenshot(name):
                    value,response=await call('desktop_observe')
                    import base64
                    picture=next(c for c in response.content if c.type=='image')
                    (output/(name+'.png')).write_bytes(base64.b64decode(picture.data))
                    (output/(name+'.json')).write_text(json.dumps(value,indent=2))
                await screenshot('alternate-screen')
                cases.append('real-alternate-screen-mode-set-and-screenshot')
                async def key(chord):await call('desktop_press_keys',window_id=wid,chord=chord)
                await key('Down');await oracle(lambda v:v['selected']==1)
                await key('Tab');await oracle(lambda v:v['focus']=='field')
                text='café $(never-execute)'
                await call('desktop_paste',window_id=wid,text=text,shortcut='ctrl_shift_v')
                await oracle(lambda v:v['field']==text and v['commits']==0)
                await key('Tab');await oracle(lambda v:v['focus']=='confirm')
                await key('Return');await oracle(lambda v:v.get('committed')=={'selected':1,'text':text} and v['commits']==1)
                await screenshot('confirmed')
                cases.append('arrows-tab-literal-field-and-explicit-confirmation')
                await key('Escape');state=await oracle(lambda v:v['phase']=='restored')
                assert state['mode_after']==2 and terminal.poll() is None,state
                windows,_=await call('desktop_windows');assert any(w['window_id']==wid for w in windows['windows'])
                await screenshot('restored-screen')
                cases.append('alternate-screen-reset-original-window-and-passive-session-survive')
                await key('q');await oracle(lambda v:v['phase']=='finished')
                cases.append('restored-session-accepts-explicit-input')
    finally:
        for process in (terminal,wm):
            if process and process.poll() is None:
                process.terminate()
                try:process.wait(timeout=3)
                except subprocess.TimeoutExpired:process.kill();process.wait(timeout=3)
        (output/'results.json').write_text(json.dumps({'passed_cases':cases,'oracle_trace':trace},indent=2))


def main():
    if os.geteuid() == 0:
        raise SystemExit('Run as ordinary desktop account')
    if len(sys.argv) == 3 and sys.argv[1] == '--child':
        return asyncio.run(child(Path(sys.argv[2])))
    output = ROOT / 'artifacts/tui' / str(time.time_ns())
    output.mkdir(parents=True)
    before = source_fingerprint(ROOT)
    with tempfile.TemporaryDirectory(prefix='luda-tui-session-') as directory:
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
