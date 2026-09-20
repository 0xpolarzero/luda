"""Real X11 ownership interference; boundary injection is explicit, not atomicity."""
import json
import ctypes
import ctypes.util
import os
from pathlib import Path
import subprocess
import tempfile
import time
from unittest.mock import patch

from luda.common import DesktopError, stop_process
from luda.desktop import Desktop

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts/clipboard'
OUT.mkdir(parents=True, exist_ok=True)
results = []


def until(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        value = predicate()
        if value:
            return value
        time.sleep(.03)
    raise AssertionError('clipboard/fixture transition timed out')


def record(case, passed, **details):
    results.append({'case': case, 'passed': bool(passed), **details})
    assert passed, results[-1]


def read(selection='clipboard'):
    return subprocess.check_output(['xclip', '-selection', selection, '-out'], timeout=2)


def manager_owner():
    # Independent Xlib oracle; Luda deliberately exposes only the two text selections.
    x = ctypes.CDLL(ctypes.util.find_library('X11'))
    x.XOpenDisplay.argtypes = [ctypes.c_char_p]
    x.XOpenDisplay.restype = ctypes.c_void_p
    x.XInternAtom.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_int]
    x.XInternAtom.restype = ctypes.c_ulong
    x.XGetSelectionOwner.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    x.XGetSelectionOwner.restype = ctypes.c_ulong
    x.XCloseDisplay.argtypes = [ctypes.c_void_p]
    display = x.XOpenDisplay(None)
    assert display, 'Independent manager oracle cannot open display'
    try:
        return x.XGetSelectionOwner(display, x.XInternAtom(display, b'CLIPBOARD_MANAGER', 0))
    finally:
        x.XCloseDisplay(display)


def suite():
    children = []
    drivers = []
    with tempfile.TemporaryDirectory(prefix='luda-clipboard-') as directory:
        root = Path(directory)
        def owner(value, selection='clipboard'):
            path = root / ('owner-' + str(time.time_ns()))
            path.write_bytes(value)
            child = subprocess.Popen(['xclip', '-quiet', '-selection', selection, '-in', str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            children.append(child)
            until(lambda: read(selection) == value)
            return child
        def fixture(delay=600):
            statepath = root / ('consumer-' + str(time.time_ns()) + '.json')
            child = subprocess.Popen(['/usr/bin/python3', str(ROOT / 'tests/clipboard_consumer.py'), str(statepath), str(delay)])
            children.append(child)
            driver = Desktop()
            drivers.append(driver)
            window = until(lambda: next((w for w in driver.list_windows() if w['pid'] == child.pid), None))
            driver.activate(window['window_id'])
            until(statepath.exists)
            return driver, window['window_id'], lambda: json.loads(statepath.read_text())
        value = 'line one\n\t日本語 👩🏽‍💻 é\n\n'
        try:
            d, wid, state = fixture()
            record('starts-with-no-clipboard-owner', d.display().selection_owner() is None)
            owner(b'PRIMARY sentinel', 'primary')
            response = d.paste(wid, value)
            until(lambda: state()['received'])
            record('slow-consumer-exact-multiline', state()['received'] == [value] and response['effect'] == 'dispatched')
            record('primary-preserved', read('primary') == b'PRIMARY sentinel')
            # A consumer can request repeatedly; no fixed paste-duration expiry.
            d.key(wid, 'ctrl+v')
            until(lambda: len(state()['received']) == 2)
            record('owner-retained-for-repeat-consumer', state()['received'] == [value, value])
            original_target = d.target_window
            calls = 0
            def replace_before_final_check(*args, **kwargs):
                nonlocal calls
                calls += 1
                result = original_target(*args, **kwargs)
                if calls == 2:
                    owner(b'competing application text')
                return result
            before = state()['requests']
            with patch.object(d, 'target_window', side_effect=replace_before_final_check):
                try:
                    d.paste(wid, value)
                except DesktopError as exc:
                    record('preflight-owner-replacement-refused', exc.code == 'CLIPBOARD_CHANGED' and exc.effect == 'uncertain')
                else:
                    record('preflight-owner-replacement-refused', False)
            record('preflight-refusal-sends-no-shortcut', state()['requests'] == before)
            # Deterministic boundary: after the sampled comparison, before X input.
            original_key = d.key
            def replace_after_check(*args, **kwargs):
                owner(b'intervened after sample')
                return original_key(*args, **kwargs)
            count = len(state()['received'])
            with patch.object(d, 'key', side_effect=replace_after_check):
                response = d.paste(wid, value)
            until(lambda: len(state()['received']) > count)
            record('post-sample-interference-not-claimed-verified', state()['received'][-1] == 'intervened after sample' and response['effect'] == 'dispatched', verification=response['clipboard_verification'])
            # Different Luda controllers share the X selection: slow consumption
            # can receive a newer operation's bytes; each response stays dispatched.
            second = Desktop()
            drivers.append(second)
            second_wid = next(w['window_id'] for w in second.list_windows() if w['xid'] == d.target_window(wid)['xid'])
            count = len(state()['received'])
            first_response = d.paste(wid, 'first controller')
            second_response = second.paste(second_wid, 'second controller')
            until(lambda: len(state()['received']) >= count + 2)
            record('two-controllers-do-not-claim-delivery', state()['received'][-2:] == ['second controller', 'second controller'] and first_response['effect'] == second_response['effect'] == 'dispatched')
            # Stop the actual owner before the final guard; no key can be sent.
            calls = 0
            def kill_before_check(*args, **kwargs):
                nonlocal calls
                calls += 1
                result = original_target(*args, **kwargs)
                if calls == 2:
                    stop_process(d.clipboard_owner)
                return result
            before = state()['requests']
            with patch.object(d, 'target_window', side_effect=kill_before_check):
                try:
                    d.paste(wid, value)
                except DesktopError as exc:
                    record('dead-owner-refused-before-shortcut', exc.code == 'CLIPBOARD_CHANGED' and state()['requests'] == before)
                else:
                    record('dead-owner-refused-before-shortcut', False)
            closing, closing_wid, closing_state = fixture(delay=1200)
            response = closing.paste(closing_wid, value)
            closing.close()
            until(lambda: closing_state()['received'])
            record('server-close-before-consumption-not-delivery', closing_state()['received'] == [None] and response['effect'] == 'dispatched')
            d.activate(wid)
            large = '日本語 😀\n' * 20000
            count = len(state()['received'])
            response = d.paste(wid, large)
            until(lambda: len(state()['received']) > count)
            record('large-payload-transfer-exact', state()['received'][-1] == large and response['effect'] == 'dispatched', utf8_bytes=len(large.encode()))
            # Actual clipboard manager, isolated by the surrounding session.
            manager = subprocess.Popen(['xfce4-clipman'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            children.append(manager)
            until(manager_owner)
            count = len(state()['received'])
            response = d.paste(wid, value)
            until(lambda: len(state()['received']) > count)
            record('xfce-clipman-exact-delayed-consumer', state()['received'][-1] == value and response['effect'] == 'dispatched')
            record('manager-does-not-alter-primary', read('primary') == b'PRIMARY sentinel')
        finally:
            for driver in drivers:
                driver.close()
            for child in reversed(children):
                if child.poll() is None:
                    child.terminate()
                    child.wait(timeout=3)


if __name__ == '__main__':
    try:
        suite()
    except Exception as exc:
        results.append({'case': 'suite-completion', 'passed': False, 'error_type': type(exc).__name__})
        raise
    finally:
        (OUT / 'results.json').write_text(json.dumps(results, indent=2) + '\n')
        print(json.dumps(results, indent=2))
