"""Research only: call AT-SPI directly behind Luda's foreground policy.

Run on a NEW private Xvfb and D-Bus session (see BACKGROUND-EXPERIENCE.md).
This deliberately does not add a public background-input capability.
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

ROOT = Path(__file__).resolve().parents[2]


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
    output = ROOT / 'artifacts/background-semantics'
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

            def direct(w, eid, op, **args):
                # Bypass ONLY the public foreground policy for this experiment.
                return d.ax({'op': op, 'pid': w['pid'], 'start': w['start'],
                             'target': d.elements[eid]['node'], **args}, True)

            d.activate(ow['window_id'])
            eid = element(sw, 'Contract text')
            before = desktop_state()
            try:
                d.element(eid, 'set', text='background probe')
            except DesktopError as exc:
                assert exc.code == 'FOCUS_CHANGED', exc.code
            else:
                raise AssertionError('Current public foreground policy unexpectedly changed')
            assert oracle('semantic/state.json')['text'] == ''
            assert desktop_state() == before
            rows.append({'case': 'public-background-mutation-refused', 'passed': True})

            result = direct(sw, eid, 'set', text='background probe')
            wait(lambda: oracle('semantic/state.json')['text'] == 'background probe')
            assert result['exact_match'] and desktop_state() == before
            rows.append({'case': 'direct-background-text-with-independent-app-readback',
                         'passed': True, 'before_after_desktop_unchanged': True})

            d.activate(sw['window_id'])
            eid = element(ow, 'Proof action')
            before = desktop_state()
            result = direct(ow, eid, 'invoke', action='click')
            wait(lambda: oracle('overlay.json')['proof'] == 1)
            assert result['effect'] == 'dispatched' and desktop_state() == before
            rows.append({'case': 'direct-background-button-with-independent-app-counter',
                         'passed': True, 'before_after_desktop_unchanged': True})

            # Counterexample: a target-local action can itself request foreground.
            eid = element(ow, 'Show attention window')
            before = desktop_state()
            result = direct(ow, eid, 'invoke', action='click')
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
        evidence = {'scope': 'research only; two GTK3 fixtures on private Xvfb/XFWM',
                    'uid': os.getuid(), 'cases': rows, 'cleanup_errors': cleanup_errors,
                    'limits': ['Before/after observations do not exclude transient interference.',
                               'No simultaneous human input, preview, pixel input, or toolkit-wide qualification.',
                               'Public Luda background mutation remains unsupported.']}
        (output / 'results.json').write_text(json.dumps(evidence, indent=2) + '\n')
        print(json.dumps(evidence, indent=2))
        if cleanup_errors:
            raise RuntimeError('Private background probe cleanup failed; see results')


if __name__ == '__main__':
    main()
