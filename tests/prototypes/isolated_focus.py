"""Source-informed mechanism probe; not production toolkit qualification.

LUDA_ISOLATED_TEST_DISPLAY=1 LUDA_TEST_UID=$(id -u) xvfb-run -a \\
  -s '-screen 0 1000x700x24 -nolisten tcp' dbus-run-session -- \\
  .venv/bin/python tests/prototypes/isolated_focus.py [normal|restore|ax_focus]

LUDA_CORE_EVENTS=1 exercises the old focus-stealing control.
LUDA_HUMAN_SHIFT=1 holds human Shift throughout input.
LUDA_FOCUS_OUTPUT selects the JSON evidence path.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time

HERE = Path(__file__).resolve().parent


def command(*args):
    return subprocess.check_output(list(map(str, args)), text=True, timeout=5).strip()


def main():
    if (os.environ.get('LUDA_ISOLATED_TEST_DISPLAY') != '1'
            or os.environ.get('LUDA_TEST_UID') != str(os.getuid())
            or int(os.environ['DISPLAY'].split(':')[1].split('.')[0]) < 2):
        raise SystemExit('Requires an explicitly selected test UID and new private Xvfb.')
    case = sys.argv[1] if len(sys.argv) > 1 else 'normal'
    if case not in ('normal', 'restore', 'ax_focus'):
        raise SystemExit('Choose normal, restore, or ax_focus.')
    children, thread = [], None
    stop = threading.Event()
    sent = [0]
    with tempfile.TemporaryDirectory(prefix='luda-focus-') as directory:
        base = Path(directory)
        for key in ('XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'XDG_CACHE_HOME', 'XDG_RUNTIME_DIR'):
            (base / key).mkdir(mode=0o700)
            os.environ[key] = str(base / key)
        helper = base / 'input'
        command('gcc', HERE / 'isolated_focus.c', '-o', helper, '-lXi', '-lXtst', '-lX11')

        def launch(*args):
            children.append(subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL))

        def oracle(name):
            return json.loads((base / f'{name}.json').read_text())

        def click(name, control, agent=True):
            x, y = oracle(name)['bounds'][control]
            if agent:
                command(helper, 'click', x, y, 1)
            else:
                command('xdotool', 'mousemove', x, y, 'click', 1)

        try:
            launch('xfwm4', '--compositor=off')
            time.sleep(1)
            for name in ('agent', 'human'):
                launch('/usr/bin/python3', str(HERE / 'independent_input_fixture.py'), str(base / f'{name}.json'), name)
            time.sleep(1)
            ids = {name: command('xdotool', 'search', '--name', f'^{name}$') for name in ('agent', 'human')}
            for name, x in (('agent', 50), ('human', 500)):
                command('xdotool', 'windowmove', ids[name], x, 100)
            command('xdotool', 'windowactivate', '--sync', ids['human'])
            time.sleep(.2)
            click('human', 'entry', False)
            command(helper, 'add')
            time.sleep(.2)
            initial_focus = command('xdotool', 'getwindowfocus')

            def human():
                while not stop.is_set():
                    command('xdotool', 'key', 'b')
                    sent[0] += 1
                    time.sleep(.02)

            if os.getenv('LUDA_HUMAN_SHIFT'):
                command('xdotool', 'keydown', 'Shift_L')
            thread = threading.Thread(target=human)
            thread.start()
            actions = ['click', 'entry', 'type', 'popup', 'close']
            if case == 'restore':
                actions = ['minimize', 'restore'] + actions
            elif case == 'ax_focus':
                actions = ['ax_focus', 'type']
            rows = []
            for action in actions:
                before = command('xdotool', 'getwindowfocus')
                if action == 'minimize':
                    command('xdotool', 'windowminimize', ids['agent'])
                elif action == 'restore':
                    from luda.x11 import X11
                    display = X11()
                    window = int(ids['agent'])
                    display.map_without_focus(window, display.window_tokens([window])[window])
                elif action == 'ax_focus':
                    command('/usr/bin/python3', HERE / 'isolated_focus_ax.py')
                elif action in ('click', 'entry', 'popup'):
                    click('agent', {'click': 'button', 'entry': 'entry', 'popup': 'menu_button'}[action])
                else:
                    command(helper, 'type', ids['agent'], 'a' if action == 'type' else 'Escape')
                time.sleep(.3)
                rows.append({'action': action, 'before_focus': before, 'after_focus': command('xdotool', 'getwindowfocus'),
                             'agent': oracle('agent'), 'human': oracle('human')})
            stop.set()
            thread.join(timeout=6)
            time.sleep(.1)
            result = {'case': case, 'uid': os.getuid(), 'send_core': bool(os.getenv('LUDA_CORE_EVENTS')),
                      'human_shift': bool(os.getenv('LUDA_HUMAN_SHIFT')), 'sent': sent[0],
                      'human_text': oracle('human')['text'], 'initial_focus': initial_focus, 'rows': rows}
            output = Path(os.getenv('LUDA_FOCUS_OUTPUT', 'artifacts/isolated-focus/results.json'))
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(result, indent=2) + '\n')
            if not os.getenv('LUDA_CORE_EVENTS') and case != 'ax_focus':
                assert result['human_text'] == ('B' if os.getenv('LUDA_HUMAN_SHIFT') else 'b') * sent[0]
                by_action = {row['action']: row for row in rows}
                assert by_action['click']['agent']['clicks'] == 1
                assert by_action['type']['agent']['text'] == 'a'
                assert by_action['popup']['agent']['menu_visible']
                assert not by_action['close']['agent']['menu_visible']
                assert all(row['after_focus'] == initial_focus for row in rows)
            print(json.dumps({'sent': sent[0], 'received': len(result['human_text']), 'output': str(output)}))
        finally:
            stop.set()
            if thread is not None:
                thread.join(timeout=6)
            for child in reversed(children):
                child.terminate()
                try:
                    child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=3)


if __name__ == '__main__':
    main()
