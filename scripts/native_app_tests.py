#!/usr/bin/env python3
"""Run native app suites in independently owned X11/D-Bus sessions."""
import argparse
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time

from headless_tests import stop
from qualify import source_fingerprint

ROOT = Path(__file__).resolve().parents[1]
SUITES = {
    'mousepad-files': 'live_file_workflows.py',
    'thunar-files': 'live_thunar.py',
    'window-states': 'live_interaction.py',
    'mcp-applications': 'live_mcp_applications.py',
}


def bounded(command, env, log, timeout):
    child = subprocess.Popen(command, env=env, cwd=ROOT, stdout=log,
                             stderr=log, start_new_session=True)
    try:
        code = child.wait(timeout=timeout)
        return {'status': 'passed' if code == 0 else 'failed', 'returncode': code}
    except subprocess.TimeoutExpired:
        return {'status': 'timeout', 'returncode': None}
    finally:
        # Reap the whole owned group even when the launcher already exited.
        stop(child)


def inside(suite):
    wm = subprocess.Popen(['xfwm4', '--compositor=off'])
    try:
        deadline = time.monotonic() + 10
        while True:
            ready = subprocess.run(['wmctrl', '-m'], capture_output=True, timeout=2)
            if ready.returncode == 0:
                break
            if wm.poll() is not None or time.monotonic() >= deadline:
                raise RuntimeError('Private window manager did not become ready')
            time.sleep(.1)
        return subprocess.call([sys.executable, str(ROOT / 'tests' / SUITES[suite])], cwd=ROOT)
    finally:
        wm.terminate()
        try:
            wm.wait(timeout=3)
        except subprocess.TimeoutExpired:
            wm.kill()
            wm.wait(timeout=3)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inside', choices=SUITES, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if os.geteuid() == 0:
        parser.error('Run as an ordinary user; root bypasses the read-only fixture.')
    if args.inside:
        return inside(args.inside)
    output = ROOT / 'artifacts/native-apps'
    output.mkdir(parents=True, exist_ok=True)
    results = []
    evidence = {'schema_version': 1, 'source': source_fingerprint(ROOT),
                'environment': {'architecture': platform.machine(),
                                'python': platform.python_version(),
                                'distribution': platform.freedesktop_os_release(),
                                'uid': os.getuid(), 'backend': 'one private Xvfb/D-Bus/Xfwm4 session per suite'},
                'suites': results}
    packages = subprocess.run(['dpkg-query', '-W', 'mousepad', 'thunar', 'xfwm4', 'xvfb',
                               'at-spi2-core', 'python3-gi', 'dbus-x11'],
                              capture_output=True, text=True, timeout=10)
    evidence['environment']['packages'] = packages.stdout.splitlines()
    try:
        for suite in SUITES:
            began = time.monotonic()
            with tempfile.TemporaryDirectory(prefix='luda-native-ci-') as directory:
                private = Path(directory)
                env = dict(os.environ, NO_AT_BRIDGE='0', GSETTINGS_BACKEND='memory')
                for key, suffix in [('XDG_CONFIG_HOME', 'config'), ('XDG_DATA_HOME', 'data'),
                                    ('XDG_CACHE_HOME', 'cache'), ('XDG_RUNTIME_DIR', 'runtime')]:
                    path = private / suffix
                    path.mkdir(mode=0o700)
                    env[key] = str(path)
                # Inherited session variables must not select any user desktop.
                for key in ('DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS', 'SESSION_MANAGER'):
                    env.pop(key, None)
                with (output / f'{suite}.log').open('wb') as log:
                    result = bounded(['xvfb-run', '-a', '-s', '-screen 0 1440x1000x24 -nolisten tcp',
                                      'dbus-run-session', '--', sys.executable, str(Path(__file__).resolve()),
                                      '--inside', suite], env, log, 120)
                results.append({'suite': suite, **result, 'seconds': round(time.monotonic() - began, 3)})
    finally:
        evidence['source_after'] = source_fingerprint(ROOT)
        evidence['source_unchanged'] = evidence['source'] == evidence['source_after']
        (output / 'results.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print(json.dumps(results, indent=2))
    return 0 if evidence['source_unchanged'] and len(results) == len(SUITES) and all(r['status'] == 'passed' for r in results) else 1


if __name__ == '__main__':
    sys.exit(main())
