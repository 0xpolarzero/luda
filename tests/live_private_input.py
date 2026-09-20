"""Actual MCP plus independent GTK files and a concurrent human X connection.

Run with .venv/bin/python tests/live_private_input.py. Always creates private
Xvfb/D-Bus; never operates on the shared desktop. Writes honest per-case results.
"""
import asyncio
import ctypes as C
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
from PIL import ImageGrab
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from live_keyboard_guard import Oracle, wait

ROOT = Path(__file__).resolve().parents[1]

async def child():
    children, cases, failures = [], [], []
    oracle = None
    output = ROOT / 'artifacts/private-input'
    output.mkdir(parents=True, exist_ok=True)
    def command(*argv):
        return subprocess.check_output(argv, text=True, timeout=3).strip()
    def launch(*argv):
        process = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        children.append(process)
        return process
    try:
        with tempfile.TemporaryDirectory(prefix='luda-private-fixture-') as directory:
            base = Path(directory)
            launch('xfwm4', '--compositor=off')
            wait(lambda: subprocess.run(['wmctrl', '-m'], capture_output=True).returncode == 0)
            for name in ('agent', 'human'):
                launch('/usr/bin/python3', str(ROOT/'tests/private_input_fixture.py'), str(base/f'{name}.json'), f'Luda private {name}')
            wait(lambda: all((base/f'{name}.json').exists() for name in ('agent', 'human')))
            def state(name='agent'):
                return json.loads((base/f'{name}.json').read_text())
            agent = command('xdotool', 'search', '--name', '^Luda private agent$')
            human = command('xdotool', 'search', '--name', '^Luda private human$')
            command('xdotool', 'windowmove', agent, '40', '100')
            command('xdotool', 'windowmove', human, '750', '100')
            command('xdotool', 'windowactivate', '--sync', human)
            command('xdotool', 'mousemove', '1300', '800')
            oracle = Oracle()
            def human_state():
                return {'focus': command('xdotool', 'getwindowfocus', '-f'),
                        'pointer': command('xdotool', 'getmouselocation', '--shell'),
                        'keys': sorted(oracle.pressed()), 'buttons': oracle.buttons()}
            initial = human_state()
            params = StdioServerParameters(command=str(ROOT/'.venv/bin/luda'), env=dict(os.environ))
            async with stdio_client(params) as streams:
                async with ClientSession(*streams) as client:
                    await client.initialize()
                    async def call(tool, **arguments):
                        response = await client.call_tool(tool, arguments)
                        value = json.loads(response.content[0].text)
                        assert not response.isError, (tool, value)
                        return value
                    windows = (await call('desktop_windows'))['windows']
                    wid = next(w['window_id'] for w in windows if w['xid'] == int(agent))
                    async def point(tool, control, **extra):
                        shot = await call('desktop_observe', max_width=2560)
                        x, y = state()['bounds'][control]
                        return await call(tool, window_id=wid, snapshot_id=shot['snapshot_id'], x=x, y=y, **extra)
                    async def case(name, operation):
                        before = human_state()
                        samples, stopped = [], threading.Event()
                        def sample_focus():
                            observer = Oracle()
                            observer.x.XGetInputFocus.argtypes = [C.c_void_p, C.POINTER(C.c_ulong), C.POINTER(C.c_int)]
                            try:
                                while not stopped.is_set():
                                    focus, revert = C.c_ulong(), C.c_int()
                                    observer.x.XGetInputFocus(observer.d, C.byref(focus), C.byref(revert))
                                    if str(focus.value) != before['focus']:
                                        samples.append(focus.value)
                                    stopped.wait(.005)
                            finally:
                                observer.close()
                        monitor = threading.Thread(target=sample_focus)
                        monitor.start()
                        try:
                            await operation()
                            await asyncio.sleep(.12)
                            after = human_state()
                            assert after == before, {'before':before, 'after':after}
                            assert not samples, {'transient_human_focus_changes': samples[:20]}
                            cases.append(name)
                        except Exception as exc:
                            failures.append({'case':name, 'error':repr(exc), 'human':human_state()})
                            command('xdotool', 'windowactivate', '--sync', human)
                            command('xdotool', 'mousemove', '1300', '800')
                        finally:
                            stopped.set(); monitor.join(timeout=2)
                    async def click():
                        count = state()['clicks']
                        await point('desktop_click', 'button')
                        wait(lambda: state()['clicks'] == count+1)
                        x, y = state()['bounds']['button']
                        assert ImageGrab.grab(xdisplay=os.environ['DISPLAY']).getpixel((x+1,y+6)) == (255,85,170)
                    await case('click preserves human pointer, focus and device state', click)
                    async def hover_scroll():
                        await point('desktop_hover', 'area')
                        previous = state()['scrolls']
                        await point('desktop_scroll', 'area', direction='down', ticks=3)
                        wait(lambda: state()['scrolls'] == previous+3)
                    await case('hover and three wheel ticks preserve human devices', hover_scroll)
                    async def type_keys():
                        await point('desktop_click', 'entry')
                        await call('desktop_press_keys', window_id=wid, chord='a', count=3)
                        wait(lambda: state()['text'].endswith('aaa'))
                    await case('typing reaches agent entry without changing human focus', type_keys)
                    async def held_human():
                        command('xdotool', 'keydown', 'Shift_L')
                        try:
                            before = human_state()
                            await call('desktop_press_keys', window_id=wid, chord='b')
                            wait(lambda: state()['text'].endswith('b'))
                            assert human_state() == before
                        finally:
                            command('xdotool', 'keyup', 'Shift_L')
                    await case('human held Shift does not block or uppercase agent key', held_human)
                    async def held_mouse():
                        command('xdotool', 'mousedown', '1')
                        try:
                            before = human_state()
                            await call('desktop_press_keys', window_id=wid, chord='d')
                            wait(lambda: state()['text'].endswith('d'))
                            assert human_state() == before
                        finally:
                            command('xdotool', 'mouseup', '1')
                    await case('human held mouse button remains down during agent keyboard action', held_mouse)
                    async def drag():
                        previous = state()
                        x, y = previous['bounds']['area']
                        await point('desktop_drag', 'area', end_x=x+70, end_y=y+40)
                        wait(lambda: state()['releases'] == previous['releases']+1)
                        assert state()['presses'] == previous['presses']+1
                        assert state()['motions'] > previous['motions']
                    await case('drag delivers press motion release without moving human pointer', drag)
                    async def concurrent_typing():
                        await point('desktop_click', 'entry')
                        before_agent, before_human = state()['text'], state('human')['text']
                        process = launch('xdotool', 'type', '--delay', '35', 'humanhuman')
                        try:
                            await call('desktop_press_keys', window_id=wid, chord='c', count=10)
                        finally:
                            process.wait(timeout=3)
                        wait(lambda: state('human')['text'] == before_human+'humanhuman')
                        wait(lambda: state()['text'] == before_agent+'c'*10)
                    await case('concurrent human and agent typing reach separate applications', concurrent_typing)
                    async def popup():
                        await point('desktop_click', 'menu_button')
                        wait(lambda: state()['menu_visible'])
                        before_human = state('human')['text']
                        command('xdotool', 'type', '--delay', '10', 'menuhuman')
                        wait(lambda: state('human')['text'] == before_human+'menuhuman')
                        # Use keyboard navigation while GTK's own private grab is active.
                        await call('desktop_press_keys', window_id=wid, chord='Down')
                        await call('desktop_press_keys', window_id=wid, chord='Return')
                        wait(lambda: state()['menu_actions'] == 1)
                    await case('agent menu leaves human typing usable and activates exactly once', popup)
                    async def stale():
                        shot = await call('desktop_observe', max_width=2560)
                        previous = state()['clicks']
                        x, y = state()['bounds']['button']
                        command('xdotool', 'windowmove', agent, '60', '100')
                        response = await client.call_tool('desktop_click', {'window_id':wid,
                            'snapshot_id':shot['snapshot_id'], 'x':x, 'y':y})
                        value = json.loads(response.content[0].text)
                        assert response.isError and value['code'] == 'STALE_OBSERVATION', value
                        assert state()['clicks'] == previous
                    await case('stale screenshot rejects before application input', stale)
            assert not oracle.pressed() and not oracle.buttons()
    finally:
        if oracle: oracle.close()
        for process in reversed(children):
            if process.poll() is None:
                process.terminate()
                try: process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(timeout=3)
        report = {'scope':'real MCP, private Xvfb/XFWM, GTK file oracles, independent human core connection',
                  'passed':cases, 'failed':failures, 'qualification':'bounded fixture coverage, not universal app support'}
        (output/'results.json').write_text(json.dumps(report, indent=2)+'\n')
        print(json.dumps(report, indent=2))
    assert not failures, failures

def main():
    if '--child' in sys.argv:
        assert os.environ.get('LUDA_PRIVATE_TEST') == '1' and os.environ.get('DISPLAY') != ':1'
        return asyncio.run(child())
    with tempfile.TemporaryDirectory(prefix='luda-private-session-') as directory:
        env = dict(os.environ, LUDA_PRIVATE_TEST='1', NO_AT_BRIDGE='0', GSETTINGS_BACKEND='memory')
        for key in ('XDG_CONFIG_HOME','XDG_DATA_HOME','XDG_CACHE_HOME','XDG_RUNTIME_DIR'):
            path = Path(directory)/key; path.mkdir(mode=0o700); env[key] = str(path)
        env['XDG_CONFIG_DIRS'] = env['XDG_CONFIG_HOME']
        result = subprocess.run(['xvfb-run','-a','-s','-screen 0 1400x900x24 -nolisten tcp',
                                 'dbus-run-session','--',sys.executable,__file__,'--child'], env=env, timeout=120)
        raise SystemExit(result.returncode)

if __name__ == '__main__': main()
