"""Real terminals with independent raw passive PTY input/signal oracles."""
import json
from pathlib import Path
import subprocess
import tempfile
import time

from luda.common import DesktopError
from luda.desktop import Desktop
from window_oracles import application_target

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts/terminals'
OUT.mkdir(parents=True, exist_ok=True)
results = []


def until(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(.04)
    raise AssertionError('Terminal transition timed out')


def record(case, passed, **details):
    results.append({'case': case, 'passed': bool(passed), **details})
    assert passed, results[-1]


def scenario(kind, bracketed):
    label = kind + ('-bracketed' if bracketed else '-plain')
    with tempfile.TemporaryDirectory(prefix='luda-passive-pty-') as directory:
        statefile = Path(directory) / 'state.json'
        child = ['/usr/bin/python3', str(ROOT / 'tests/passive_pty.py'), str(statefile), 'bracketed' if bracketed else 'plain']
        title = 'Luda passive ' + label
        argv = ['xterm', '-title', title, '-xrm', '*VT100.translations: #override Ctrl Shift <Key>V: insert-selection(CLIPBOARD)', '-e', *child] if kind == 'xterm' else ['xfce4-terminal', '--disable-server', '--title=' + title, '--execute', *child]
        p = subprocess.Popen(argv)
        d = Desktop()
        try:
            window = until(lambda: next((w for w in d.list_windows() if w['pid'] == p.pid and title in w['title']), None))
            wid = window['window_id']
            d.activate(wid)
            until(statefile.exists)
            def state():
                return json.loads(statefile.read_text())
            value = 'alpha\n\t日本語 👩🏽‍💻 é\n\n'
            if kind == 'xterm':
                owner = d.display().selection_owner()
                try:
                    d.paste(wid, value)
                except DesktopError as exc:
                    record(label + '-auto-shortcut-refused', exc.code == 'UNSUPPORTED_PASTE' and state()['hex'] == '' and d.display().selection_owner() == owner)
                else:
                    record(label + '-auto-shortcut-refused', False)
            result = d.paste(wid, value, 'ctrl_shift_v' if kind == 'xterm' else None)
            dialog = False
            cancelled = False
            deadline = time.monotonic() + 5
            while not state()['hex'] and time.monotonic() < deadline:
                owned = [w for w in d.list_windows() if w['pid'] == p.pid]
                target = application_target(owned, wid)
                active = next((w for w in owned if w['window_id'] == target), None)
                if active and active['window_id'] != wid:
                    tree = d.inspect(active['window_id'])
                    (OUT / (label + '-dialog.json')).write_text(json.dumps(tree, indent=2))
                    button = next((n for n in tree['nodes'] if n['role'] == 'push button' and n['name'].replace('_', '').casefold() == 'paste'), None)
                    if button:
                        record(label + '-confirmation-holds-input', state()['hex'] == '')
                        if not cancelled:
                            cancel = next(n for n in tree['nodes'] if n['role'] == 'push button' and n['name'].replace('_', '').casefold() == 'cancel')
                            d.element(cancel['element_id'], 'invoke', action=cancel['actions'][0])
                            until(lambda: application_target([w for w in d.list_windows() if w['pid'] == p.pid], wid) == wid)
                            record(label + '-confirmation-cancel-preserves-pty', state()['hex'] == '')
                            cancelled = True
                            # A new explicit operation after confirmed cancellation, not retrying uncertain input.
                            result = d.paste(wid, value)
                            deadline = time.monotonic() + 5
                            continue
                        d.element(button['element_id'], 'invoke', action=button['actions'][0])
                        dialog = True
                        break
                time.sleep(.05)
            until(lambda: state()['hex'])
            actual = bytes.fromhex(state()['hex'])
            expected_body = value.replace('\n', '\r').encode()
            expected = b'\x1b[200~' + expected_body + b'\x1b[201~' if bracketed else expected_body
            record(label + '-exact-pty-bytes', actual == expected, actual_hex=actual.hex(), expected_hex=expected.hex(), confirmation=dialog, effect=result['effect'])
            before = state()
            d.key(wid, 'ctrl+shift+c')
            if kind == 'xterm':
                # xterm has no universal copy binding: this configuration forwards Ctrl+C.
                until(lambda: state()['interrupts'] == before['interrupts'] + 1)
                record(label + '-unconfigured-copy-chord-interrupts', state()['hex'] == before['hex'])
            else:
                time.sleep(.15)
                record(label + '-copy-is-not-interrupt', state() == before)
            before = state()
            d.key(wid, 'ctrl+c')
            until(lambda: state()['interrupts'] == before['interrupts'] + 1)
            record(label + '-ctrl-c-is-interrupt', state()['hex'] == before['hex'])
        finally:
            d.close()
            if p.poll() is None:
                p.terminate()
                p.wait(timeout=5)


if __name__ == '__main__':
    try:
        for terminal in ('xterm', 'xfce4-terminal'):
            for mode in (True, False):
                scenario(terminal, mode)
    except Exception as exc:
        results.append({'case': 'suite-completion', 'passed': False, 'error_type': type(exc).__name__})
        raise
    finally:
        (OUT / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
        print(json.dumps(results, indent=2))
