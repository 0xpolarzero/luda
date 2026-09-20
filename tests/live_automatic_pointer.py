"""Actual MCP routing and visible pixels on an owned Xvfb desktop."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from PIL import ImageGrab
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from luda.desktop import Desktop
from live_keyboard_guard import Oracle, wait

ROOT = Path(__file__).resolve().parents[1]


async def child():
    cases = []
    children = []
    admin = oracle = None
    output = ROOT / 'artifacts/automatic-pointer'
    output.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix='luda-automatic-pointer-') as directory:
            base = Path(directory)
            for name in ('pointer', 'human'):
                (base / name).mkdir()
            def launch(*argv):
                process = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                children.append(process)
                return process
            def command(*argv):
                return subprocess.check_output(argv, timeout=3, text=True).strip()
            launch('xfwm4', '--compositor=off')
            wait(lambda: subprocess.run(['wmctrl', '-m'], capture_output=True, timeout=2).returncode == 0)
            target = launch('/usr/bin/python3', str(ROOT / 'tests/pointer_fixture.py'), str(base / 'pointer'))
            human = launch('/usr/bin/python3', str(ROOT / 'tests/semantic_fixture.py'), str(base / 'human'))
            admin = Desktop()
            oracle = Oracle()
            wait(lambda: len([w for w in admin.list_windows() if w['pid'] in (target.pid, human.pid)]) == 2)
            windows = admin.list_windows()
            tw = next(w for w in windows if w['pid'] == target.pid)
            hw = next(w for w in windows if w['pid'] == human.pid)
            command('wmctrl', '-ir', str(tw['xid']), '-e', '0,40,70,500,300')
            command('wmctrl', '-ir', str(hw['xid']), '-e', '0,720,70,550,500')
            wait(lambda: (base / 'pointer/state.json').exists() and (base / 'human/state.json').exists())
            def state():
                return json.loads((base / 'pointer/state.json').read_text())
            def human_front():
                admin.activate(hw['window_id'])
            parameters = StdioServerParameters(command=str(ROOT / '.venv/bin/luda'), env=dict(os.environ))
            async with stdio_client(parameters) as streams:
                async with ClientSession(*streams) as client:
                    await client.initialize()
                    async def call(name, **arguments):
                        result = await client.call_tool(name, arguments)
                        value = json.loads(result.content[0].text)
                        assert not result.isError, (name, value)
                        return value
                    async def rejected(code, **arguments):
                        before = state()
                        active = command('xdotool', 'getactivewindow')
                        response = await client.call_tool('desktop_click', arguments)
                        value = json.loads(response.content[0].text)
                        assert response.isError and value['code'] == code, value
                        assert state() == before and command('xdotool', 'getactivewindow') == active
                    windows = (await call('desktop_windows'))['windows']
                    tw = next(w for w in windows if w['pid'] == target.pid)
                    wid = tw['window_id']
                    b = tw['bounds']
                    x, y = b['x'] + 100, b['y'] + 100
                    human_front()
                    shot = await call('desktop_observe', max_width=2560)
                    assert shot['image_size'] == shot['desktop_size']
                    value = await call('desktop_click', window_id=wid, snapshot_id=shot['snapshot_id'], x=x, y=y)
                    wait(lambda: state()['presses'] == [1] and state()['releases'] == [1])
                    assert value['effect'] == 'dispatched'
                    assert int(command('xdotool', 'getactivewindow')) == tw['xid']
                    assert ImageGrab.grab(xdisplay=os.environ['DISPLAY']).getpixel((x+1, y+6)) == (255,85,170)
                    assert not oracle.buttons()
                    cases.append('MCP inactive click activates once, app receives one click, cursor pixels visible')
                    await rejected('STALE_OBSERVATION', window_id=wid, snapshot_id=shot['snapshot_id'], x=x, y=y)
                    cases.append('original screenshot is not relabelled after automatic activation')

                    # A new call hides the prior marker before checking occlusion.
                    shot = await call('desktop_observe', max_width=2560)
                    await call('desktop_click', window_id=wid, snapshot_id=shot['snapshot_id'], x=x, y=y)
                    wait(lambda: len(state()['releases']) == 2)
                    cases.append('consecutive same-point click is not blocked by the agent cursor')

                    human_front()
                    shot = await call('desktop_observe', max_width=2560)
                    await call('desktop_scroll', window_id=wid, snapshot_id=shot['snapshot_id'], x=x, y=y, direction='down', ticks=3)
                    wait(lambda: len(state()['scrolls']) == 3)
                    assert all('DOWN' in item for item in state()['scrolls'])
                    cases.append('MCP inactive scroll activates and delivers exactly three ticks')

                    human_front()
                    shot = await call('desktop_observe', max_width=2560)
                    await call('desktop_drag', window_id=wid, snapshot_id=shot['snapshot_id'], x=x, y=y, end_x=x+80, end_y=y+60)
                    wait(lambda: len(state()['releases']) == 3)
                    assert len(state()['presses']) == 3 and not oracle.buttons()
                    location = command('xdotool', 'getmouselocation', '--shell')
                    assert f'X={x+80}\nY={y+60}\n' in location
                    cases.append('MCP inactive drag reaches endpoint and releases owned button')

                    human_front()
                    shot = await call('desktop_observe', max_width=2560)
                    before = state()
                    await call('desktop_hover', window_id=wid, snapshot_id=shot['snapshot_id'], x=x, y=y)
                    assert state() == before and not oracle.buttons()
                    assert f'X={x}\nY={y}\n' in command('xdotool', 'getmouselocation', '--shell')
                    cases.append('MCP inactive hover activates without a button event')

                    human_front()
                    shot = await call('desktop_observe', max_width=2560)
                    command('wmctrl', '-ir', str(tw['xid']), '-e', '0,60,70,500,300')
                    await rejected('STALE_OBSERVATION', window_id=wid, snapshot_id=shot['snapshot_id'], x=x, y=y)
                    cases.append('external layout change refuses input without activation')

                    command('wmctrl', '-ir', str(hw['xid']), '-e', '0,40,60,600,500')
                    human_front()
                    shot = await call('desktop_observe', max_width=2560)
                    await rejected('OCCLUDED_TARGET', window_id=wid, snapshot_id=shot['snapshot_id'], x=x, y=y)
                    cases.append('covered pixel target refuses input without activation')
            # Closing MCP stdin must remove the helper and its rendered pixels.
            await asyncio.sleep(.2)
            assert not oracle.buttons()
            cases.append('MCP exit leaves no held pointer input')
    finally:
        if admin: admin.close()
        if oracle: oracle.close()
        for process in reversed(children):
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
        evidence = {'scope':'real MCP on private Xvfb/XFWM, GTK independent event files',
                    'uid':os.getuid(), 'passed':cases,
                    'limits':['Foreground pointer routes intentionally use the shared pointer.',
                              'No broad toolkit or remote viewer qualification.']}
        (output / 'results.json').write_text(json.dumps(evidence, indent=2) + '\n')
        print(json.dumps(evidence, indent=2))


def main():
    if '--child' in sys.argv:
        return asyncio.run(child())
    with tempfile.TemporaryDirectory(prefix='luda-automatic-session-') as directory:
        env = dict(os.environ, NO_AT_BRIDGE='0', GSETTINGS_BACKEND='memory')
        for key in ('XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'XDG_CACHE_HOME', 'XDG_RUNTIME_DIR'):
            path = Path(directory) / key
            path.mkdir(mode=0o700)
            env[key] = str(path)
        env['XDG_CONFIG_DIRS'] = env['XDG_CONFIG_HOME']
        result = subprocess.run(['xvfb-run','-a','-s','-screen 0 1400x900x24 -nolisten tcp',
                                 'dbus-run-session','--',sys.executable,str(Path(__file__).resolve()),'--child'],
                                env=env, timeout=90)
        raise SystemExit(result.returncode)


if __name__ == '__main__':
    main()
