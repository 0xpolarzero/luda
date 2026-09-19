#!/usr/bin/env python3
"""Run native/MCP fixtures in a fresh Xvfb + D-Bus session, never the user's display.

Usage: xvfb-run -a -s '-screen 0 1440x900x24 -nolisten tcp' dbus-run-session -- .venv/bin/python scripts/headless_tests.py
"""
import json
import os
from pathlib import Path
import platform
from qualify import source_fingerprint
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def stop(child):
    # A failed suite can exit while its fixture still lives in the suite's
    # dedicated process group. Cleanup must not depend on parent liveness.
    try:
        os.killpg(child.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        child.wait(timeout=3)
    except subprocess.TimeoutExpired:
        pass
    try:
        os.killpg(child.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    child.wait(timeout=3)


def main():
    if not os.environ.get('DISPLAY') or not os.environ.get('DBUS_SESSION_BUS_ADDRESS'):
        raise SystemExit('Use xvfb-run and dbus-run-session as documented.')
    # An explicit opt-in prevents accidentally taking over an ordinary desktop.
    if os.environ.get('LUDA_ISOLATED_TEST_DISPLAY') != '1':
        raise SystemExit('Set LUDA_ISOLATED_TEST_DISPLAY=1 only for the fresh test X server.')
    env = dict(os.environ, NO_AT_BRIDGE='0', GTK_MODULES='gail:atk-bridge')
    output = ROOT / 'artifacts/headless'
    output.mkdir(parents=True, exist_ok=True)
    results = []
    with tempfile.TemporaryDirectory(prefix='luda-test-session-') as runtime:
        env['XDG_RUNTIME_DIR'] = runtime
        with (output / 'window-manager.log').open('wb') as log:
            wm = subprocess.Popen(['xfwm4', '--compositor=off'], env=env, stdout=log, stderr=log, start_new_session=True)
            try:
                deadline = time.monotonic() + 10
                while True:
                    ready = subprocess.run(['wmctrl', '-m'], env=env, capture_output=True, timeout=2)
                    if ready.returncode == 0:
                        break
                    if wm.poll() is not None or time.monotonic() > deadline:
                        raise RuntimeError('Isolated window manager failed to become ready')
                    time.sleep(.1)
                for suite, arguments in [('native', [str(ROOT / 'tests/live_backend.py')]),
                                         ('mcp', [str(ROOT / 'tests/live_mcp.py'), '--server', str(Path(sys.executable).parent / 'luda')]),
                                         ('cancellation', [str(ROOT / 'tests/live_cancellation.py'), '--server', str(Path(sys.executable).parent / 'luda')]),
                                         ('control', [str(ROOT / 'tests/live_control.py')])]:
                    began = time.monotonic()
                    with (output / f'{suite}.log').open('wb') as suite_log:
                        child = subprocess.Popen([sys.executable, *arguments], cwd=ROOT, env=env,
                                                 stdout=suite_log, stderr=suite_log, start_new_session=True)
                        try:
                            code = child.wait(timeout=120)
                            status = 'passed' if code == 0 else 'failed'
                        except subprocess.TimeoutExpired:
                            status, code = 'timeout', None
                        finally:
                            stop(child)
                    results.append({'suite': suite, 'status': status, 'returncode': code,
                                    'seconds': round(time.monotonic() - began, 3)})
            finally:
                stop(wm)
                (output / 'results.json').write_text(json.dumps({'schema_version': 1, 'suites': results,
                    'source': source_fingerprint(ROOT),
                    'environment': {'architecture': platform.machine(), 'python': platform.python_version(),
                                    'distribution': platform.freedesktop_os_release(),
                                    'backend': 'isolated Xvfb + XFWM4 + session D-Bus',
                                    'uid': os.getuid()}}, indent=2) + '\n')
    print(json.dumps(results, indent=2))
    return 0 if len(results) == 4 and all(r['status'] == 'passed' for r in results) else 1


if __name__ == '__main__':
    sys.exit(main())
