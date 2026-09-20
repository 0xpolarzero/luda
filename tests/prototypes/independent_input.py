"""Research-only MPX probe; never run against an existing desktop.

LUDA_ISOLATED_TEST_DISPLAY=1 xvfb-run -a -s '-screen 0 1000x700x24 -nolisten tcp' \
    dbus-run-session -- .venv/bin/python tests/prototypes/independent_input.py
Requires gcc, libXi/libXtst headers, XFWM, GTK3 and xdotool.
"""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

HERE = Path(__file__).resolve().parent


def command(*args):
    return subprocess.check_output(args, text=True, timeout=3).strip()


def desktop_state():
    return {key: command(*args) for key, args in {
        'pointer': ['xdotool', 'getmouselocation', '--shell'],
        'active': ['xprop', '-root', '_NET_ACTIVE_WINDOW'],
        'focus': ['xdotool', 'getwindowfocus'],
        'stacking': ['xprop', '-root', '_NET_CLIENT_LIST_STACKING'],
    }.items()}


def main():
    display = re.fullmatch(r':([0-9]+)(?:\.[0-9]+)?', os.environ.get('DISPLAY', ''))
    if (os.environ.get('LUDA_ISOLATED_TEST_DISPLAY') != '1'
            or not os.environ.get('DBUS_SESSION_BUS_ADDRESS')
            or display is None or int(display[1]) < 2):
        raise SystemExit('Requires NEW private Xvfb/D-Bus session; never shared :1.')
    children, rows = [], []
    with tempfile.TemporaryDirectory(prefix='luda-mpx-') as directory:
        base = Path(directory)
        helper = str(base / 'input')
        command('gcc', '-Wall', str(HERE / 'independent_input.c'), '-o', helper,
                '-lXi', '-lXtst', '-lX11')
        for key in ('XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'XDG_CACHE_HOME', 'XDG_RUNTIME_DIR'):
            path = base / key
            path.mkdir(mode=0o700)
            os.environ[key] = str(path)
        command('dbus-update-activation-environment', 'XDG_CONFIG_HOME', 'XDG_DATA_HOME',
                'XDG_CACHE_HOME', 'XDG_RUNTIME_DIR')

        def launch(*args):
            child = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            children.append(child)

        def oracle(name='agent'):
            return json.loads((base / f'{name}.json').read_text())

        def click(control):
            command(helper, 'click', *map(str, oracle()['bounds'][control]), '1')

        def record(label, action):
            before, app_before = desktop_state(), oracle()
            action()
            time.sleep(.3)
            rows.append({'case': label, 'before': before, 'after': desktop_state(),
                         'agent_before': app_before, 'agent_after': oracle(),
                         'human_after': oracle('human')})

        added = False
        try:
            launch('xfwm4', '--compositor=off')
            time.sleep(1)
            for name in ('agent', 'human'):
                launch('/usr/bin/python3', str(HERE / 'independent_input_fixture.py'),
                       str(base / f'{name}.json'), name)
            time.sleep(1)
            agent = command('xdotool', 'search', '--name', '^agent$')
            human = command('xdotool', 'search', '--name', '^human$')
            command('xdotool', 'windowmove', agent, '50', '100')
            command('xdotool', 'windowmove', human, '500', '100')

            def foreground_human():
                command('xdotool', 'windowactivate', '--sync', human)
                time.sleep(.2)

            foreground_human()
            command('xdotool', 'mousemove', '600', '400')
            command(helper, 'add')
            added = True
            time.sleep(.3)
            record('independent-click-visible-background', lambda: click('button'))
            click('entry')
            time.sleep(.2)
            foreground_human()
            record('independent-keyboard-background', lambda: command(helper, 'type', agent))
            command('xdotool', 'windowmove', human, '50', '100')
            foreground_human()
            record('independent-click-covered-background', lambda: click('button'))
            command('xdotool', 'windowmove', human, '500', '100')
            foreground_human()
            record('independent-popup-visible-background', lambda: click('menu_button'))

            assert all(r['before']['pointer'] == r['after']['pointer'] for r in rows)
            assert rows[0]['agent_after']['clicks'] == 1
            assert rows[0]['before']['focus'] != rows[0]['after']['focus']
            assert rows[0]['before']['stacking'] != rows[0]['after']['stacking']
            assert rows[1]['agent_after']['text'] == 'a'
            assert rows[1]['before'] == rows[1]['after']
            assert rows[2]['agent_after']['clicks'] == 1
            assert rows[2]['human_after']['clicks'] == 1
            assert rows[3]['agent_after']['menu_visible']
            assert rows[3]['before']['focus'] != rows[3]['after']['focus']
        finally:
            if added:
                try:
                    command(helper, 'remove')
                except subprocess.SubprocessError:
                    # The private server also removes devices when it exits.
                    pass
            for child in reversed(children):
                child.terminate()
                try:
                    child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=3)
            output = HERE.parents[1] / 'artifacts/independent-input'
            output.mkdir(parents=True, exist_ok=True)
            (output / 'results.json').write_text(json.dumps(rows, indent=2) + '\n')
    print(json.dumps({'recorded_cases': len(rows), 'assertions_passed': True}))


if __name__ == '__main__':
    main()
