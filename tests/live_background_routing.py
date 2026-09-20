"""Public Luda background/foreground routing with independent GTK file oracles.

Run using LUDA_ISOLATED_TEST_DISPLAY=1 dbus-run-session -- xvfb-run -a
-s "-screen 0 1280x900x24 -nolisten tcp" .venv/bin/python tests/live_background_routing.py
"""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import time

from luda.common import DesktopError
from luda.desktop import Desktop

ROOT = Path(__file__).resolve().parents[1]


def wait(predicate, timeout=6):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        value = predicate()
        if value:
            return value
        time.sleep(.04)
    raise AssertionError('Private background probe timed out')


def command(*args):
    return subprocess.check_output(args, timeout=2, text=True).strip()


def desktop_state():
    return {
        'active': command('xdotool', 'getactivewindow'),
        'keyboard_focus': command('xdotool', 'getwindowfocus'),
        'pointer': command('xdotool', 'getmouselocation', '--shell'),
        'stacking': command('xprop', '-root', '_NET_CLIENT_LIST_STACKING'),
    }


def main():
    display = re.fullmatch(r':([0-9]+)(?:\.[0-9]+)?', os.environ.get('DISPLAY', ''))
    if (os.environ.get('LUDA_ISOLATED_TEST_DISPLAY') != '1'
            or not os.environ.get('DBUS_SESSION_BUS_ADDRESS')
            or display is None or int(display[1]) < 2):
        raise SystemExit('Use a new private Xvfb + D-Bus session; never the shared desktop.')
    rows = []
    children = []
    d = None
    output = ROOT / 'artifacts/background-routing'
    output.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix='luda-background-probe-') as directory:
            base = Path(directory)
            for key in ('XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'XDG_CACHE_HOME', 'XDG_RUNTIME_DIR'):
                path = base / key
                path.mkdir(mode=0o700)
                os.environ[key] = str(path)
            os.environ['GSETTINGS_BACKEND'] = 'memory'
            os.environ['NO_AT_BRIDGE'] = '0'
            command('dbus-update-activation-environment', 'XDG_CONFIG_HOME', 'XDG_DATA_HOME',
                    'XDG_CACHE_HOME', 'XDG_RUNTIME_DIR', 'GSETTINGS_BACKEND')

            def launch(*argv):
                child = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                children.append(child)
                return child

            launch('xfwm4', '--compositor=off')
            wait(lambda: subprocess.run(['wmctrl', '-m'], capture_output=True, timeout=2).returncode == 0)
            semantic = launch('/usr/bin/python3', str(ROOT / 'tests/semantic_fixture.py'), str(base / 'semantic'))
            overlay = launch('/usr/bin/python3', str(ROOT / 'tests/overlay_fixture.py'), str(base / 'overlay.json'))
            d = Desktop()

            def window(pid):
                return wait(lambda: next((w for w in d.list_windows() if w['pid'] == pid), None))

            sw, ow = window(semantic.pid), window(overlay.pid)
            wait(lambda: (base / 'semantic/state.json').exists() and (base / 'overlay.json').exists())

            def oracle(name):
                return json.loads((base / name).read_text())

            def element(w, name):
                return next(n['element_id'] for n in d.inspect(w['window_id'])['nodes'] if n['name'] == name)

            d.activate(ow['window_id'])
            eid = element(sw, 'Contract text')
            before = desktop_state()
            result = d.type_text(eid, 'background probe', mode='replace')
            wait(lambda: oracle('semantic/state.json')['text'] == 'background probe')
            assert result['exact_match'] and desktop_state() == before
            rows.append({'case': 'public-background-text-with-independent-app-readback',
                         'passed': True, 'before_after_desktop_unchanged': True})

            d.activate(sw['window_id'])
            eid = element(ow, 'Proof action')
            before = desktop_state()
            result = d.element(eid, 'invoke')
            wait(lambda: oracle('overlay.json')['proof'] == 1)
            assert result['effect'] == 'dispatched' and desktop_state() == before
            rows.append({'case': 'public-background-button-with-independent-app-counter',
                         'passed': True, 'before_after_desktop_unchanged': True})

            # Key fallback activates the background window and reaches its field.
            d.activate(sw['window_id'])
            eid = element(sw, 'Contract text')
            d.element(eid, 'focus')
            d.activate(ow['window_id'])
            before_pointer = command('xdotool', 'getmouselocation', '--shell')
            d.key(sw['window_id'], 'End')
            d.key(sw['window_id'], 'exclam')
            wait(lambda: oracle('semantic/state.json')['text'] == 'background probe!')
            assert d.target_window(sw['window_id'])['active']
            assert command('xdotool', 'getmouselocation', '--shell') == before_pointer
            rows.append({'case': 'automatic-key-foreground-independent-text-oracle', 'passed': True})

            d.activate(ow['window_id'])
            d.paste(sw['window_id'], ' pasted')
            wait(lambda: oracle('semantic/state.json')['text'] == 'background probe! pasted')
            rows.append({'case': 'automatic-paste-foreground-independent-text-oracle', 'passed': True})

            # The independent user stream types into a different foreground app
            # while Luda mutates two background apps through their public tools.
            user = launch('/usr/bin/python3', str(ROOT / 'tests/semantic_fixture.py'), str(base / 'user'))
            uw = window(user.pid)
            wait(lambda: (base / 'user/state.json').exists())
            d.activate(uw['window_id'])
            d.element(element(uw, 'Contract text'), 'focus')
            text_id = element(sw, 'Contract text')
            action_id = element(ow, 'Proof action')
            before = desktop_state()
            old_count = oracle('overlay.json')['proof']
            user_text = 'User keeps typing while Luda works'
            user_input = launch('xdotool', 'type', '--delay', '80', '--', user_text)
            d.type_text(text_id, 'concurrent background replacement', mode='replace')
            d.element(action_id, 'invoke')
            while user_input.poll() is None:
                assert desktop_state() == before
                time.sleep(.02)
            assert user_input.returncode == 0
            wait(lambda: oracle('user/state.json')['text'] == user_text)
            wait(lambda: oracle('semantic/state.json')['text'] == 'concurrent background replacement')
            wait(lambda: oracle('overlay.json')['proof'] == old_count + 1)
            assert desktop_state() == before
            rows.append({'case': 'concurrent-user-typing-and-background-set-invoke',
                         'passed': True, 'user_text_exact': True,
                         'target_action_count_delta': 1, 'sampled_desktop_unchanged': True})

            # Counterexample: a target-local action can itself request foreground.
            eid = element(ow, 'Show attention window')
            before = desktop_state()
            result = d.element(eid, 'invoke')
            notice = wait(lambda: next((w for w in d.list_windows()
                          if w['pid'] == overlay.pid and w['title'] == 'Luda attention notification'
                          and w['active']), None))
            assert result['effect'] == 'dispatched' and notice['xid'] != int(before['active'])
            rows.append({'case': 'application-action-can-steal-focus', 'passed': True,
                         'background_noninterference': False})
    finally:
        cleanup_errors = []
        if d:
            try:
                d.close()
            except Exception as exc:
                cleanup_errors.append(type(exc).__name__)
        for child in reversed(children):
            try:
                if child.poll() is None:
                    child.terminate()
                    try:
                        child.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait(timeout=3)
            except Exception as exc:
                cleanup_errors.append(type(exc).__name__)
        evidence = {'scope': 'public Luda API; two GTK3 fixtures on private Xvfb/XFWM',
                    'uid': os.getuid(), 'cases': rows, 'cleanup_errors': cleanup_errors,
                    'limits': ['Before/after observations do not exclude transient interference.',
                               'Concurrent input is a synthetic X11 user stream; no preview, pixel input, or toolkit-wide qualification.',
                               'No production-wide qualification is claimed.']}
        (output / 'results.json').write_text(json.dumps(evidence, indent=2) + '\n')
        print(json.dumps(evidence, indent=2))
        if cleanup_errors:
            raise RuntimeError('Private background probe cleanup failed; see results')


if __name__ == '__main__':
    main()
