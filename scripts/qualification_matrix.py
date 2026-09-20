#!/usr/bin/env python3
"""Opt-in broad qualification; failures stay failures, with isolated per-suite state."""
import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import uuid

from headless_tests import stop
from qualify import source_fingerprint

ROOT = Path(__file__).resolve().parents[1]
TOKEN_KEY = 'LUDA_MATRIX_PROCESS_TOKEN'


def suite(script, ids, *, wm=True, browser=None, electron=None, firefox=None, modules=('Gtk', 'Atspi'), artifacts=(), gaps=()):
    return {'script': script, 'related_requirements': ids.split(), 'runner_window_manager': wm,
            'browser_argument': browser, 'electron_argument': electron, 'firefox_argument': firefox, 'modules': modules, 'artifact_directories': artifacts,
            'known_gaps': gaps}


SUITES = {
    'password-manager': suite('live_password_manager.py', 'AUTH-03', wm=False, artifacts=('password-manager',), gaps=('Actual native KeePassXC entry menu through Desktop methods; no GUI unlock or browser extension qualification',)),
    'dead-compose': suite('live_dead_compose.py', 'KEY-10', wm=False, artifacts=('dead-compose',), gaps=('Explicit no-input refusal of named dead-key and Compose requests; not composition support',)),
    'cpu-pressure': suite('live_cpu_pressure.py', 'PERF-10', wm=False, artifacts=('cpu-pressure',), gaps=('One CPU, nice15 desktop and two bounded nice0 load workers; no system-wide CPU/OOM qualification',)),
    'mcp': suite('live_mcp.py', 'MCP-02 MCP-03 MCP-04 MCP-05 MCP-06 MCP-07 DIAG-10 SHIP-08', artifacts=('mcp',)),
    'tui': suite('live_tui.py', 'TERM-09', wm=False, artifacts=('tui',)),
    'ax-deadline': suite('live_ax_deadline.py', 'AX-07', wm=False, artifacts=('ax-deadline',), gaps=('Stopped-provider call completes under earlier libatspi timeout; does not exercise the five-second worker kill path',)),
    'single-line': suite('live_single_line.py', 'EDIT-05', browser='--executable', modules=('Gtk','Atspi','PyQt5'), artifacts=('single-line',)),
    'tray': suite('live_tray.py', 'MENU-07', wm=False, artifacts=('tray',), gaps=('Observed private XFCE tray screenshot workflow; semantic icon/menu ownership unavailable',)),
    'undo': suite('live_undo.py', 'EDIT-06', artifacts=('undo','files')),
    'rtl': suite('live_rtl.py', 'DATA-10', wm=False, artifacts=('rtl',)),
    'thunar-drag': suite('live_thunar_drag.py', 'PTR-09', artifacts=('thunar-drag',), gaps=('Thunar 4.18 native right-drag menu with screenshot-derived rows; requires thunar, no modifier or cross-filesystem qualification',)),
    'nested-scroll': suite('live_nested_scroll.py', 'PTR-05', artifacts=('nested-scroll',)),
    'detached-menu': suite('live_detached_menu.py', 'MENU-08', artifacts=('detached-menu',), gaps=('Native GTK3 tear-off fixture and observed screenshot row only; no tray or other toolkit qualification',)),
    'mcp-disconnect': suite('live_mcp_disconnect.py', 'MCP-08', artifacts=('mcp-disconnect',), gaps=('Real stdin EOF only; no claim to undo delivered input or arbitrary network disconnection',)),
    'image-editor': suite('live_image_editor.py', 'APPS-09 APPS-10', wm=False, artifacts=('image-editor',)),
    'session-input': suite('live_session_input.py', 'AUTH-09', artifacts=('session-input',)),
    'resource-limits': suite('live_resource_limits.py', 'PERF-10 ERR-06', artifacts=('resource-limits',)),
    'bus-generation': suite('live_bus_generation.py', 'ENV-08 FAULT-04 STATE-02 SEM-09', artifacts=('bus-generation',)),
    'data-entry': suite('live_data_entry.py', 'DATA-05 DATA-06 DATA-08 DATA-09', wm=False, artifacts=('data-entry',)),
    'file-destinations': suite('live_file_destinations.py', 'FILE-10', artifacts=('file-destinations','files')),
    'browser-download': suite('live_browser_download.py', 'FILE-09', browser='--executable', artifacts=('browser-download',), gaps=('Native chooser may lack accessibility; fixed-layout screenshot workflow qualified, interruption/resume not qualified',)),
    'overlays': suite('live_overlays.py', 'MENU-05 MENU-06 MENU-10', artifacts=('overlays',)),
    'auth': suite('live_auth.py', 'AUTH-04 AUTH-05 AUTH-06 AUTH-07 AUTH-10', browser='--browser', artifacts=('auth',), gaps=('Unmasked OTP has no nonretention guarantee; window metadata does not attest OAuth origin/session; same-window content can invalidate visual intent',)),
    'data-controls': suite('live_data.py', 'DATA-01 DATA-02 DATA-04 AX-01 AX-06', wm=False, artifacts=('data',), gaps=('GTK cell edit action can be ineffective and transient editor absent from AX; explicit GUI clipboard workflow is verified separately',)),
    'injector-reuse': suite('live_injector_reuse.py', 'KEY-08 LIFE-05', wm=False, artifacts=('injector-reuse',)),
    'firefox': suite('live_firefox.py', 'WEB-02 EDIT-01 EDIT-02 EDIT-03 EDIT-09 SEM-04 AX-09', wm=False, firefox='--executable', artifacts=('firefox',), gaps=('Gecko protected input lacks functional native EditableText; explicit secret case remains failing',)),
    'mcp-input-recovery': suite('live_mcp_input_recovery.py', 'KEY-08 ERR-09 STATE-02 CONC-05 FAULT-05', wm=False, artifacts=('mcp-input-recovery',)),
    'electron': suite('live_electron.py', 'AX-04 APPS-04 EDIT-01 EDIT-02 AX-09 SEM-04', electron='--executable', artifacts=('electron',), gaps=('Electron 44.4.3 embedded Chromium152 cannot verify non-BMP selections; required replacement remains failing', 'Protected secret input lacks EditableText')),
    'semantic': suite('live_semantic.py', 'AX-01 EDIT-01 EDIT-02 EDIT-03 EDIT-09 SEM-04 SEM-05 SEM-06 SEM-07 SEM-08 DATA-03', artifacts=('semantic',)),
    'toolkits': suite('live_toolkits.py', 'AX-02 AX-03 APPS-03 EDIT-09 WIN-06', modules=('Gtk', 'Gtk4', 'Atspi', 'PyQt5'), artifacts=('toolkits',), gaps=('GTK4 provider selection/check limitations',)),
    'protected-options': suite('live_controls.py', 'AX-09 SEM-04 SEM-05', modules=('Gtk', 'Atspi', 'PyQt5'), artifacts=('controls',)),
    'combos': suite('live_combo.py', 'SEM-05', modules=('Gtk', 'Atspi', 'PyQt5'), artifacts=('combo',), gaps=('Qt combo commit is explicitly unsupported',)),
    'browser': suite('live_browser.py', 'WEB-01 WEB-02 WEB-03 WEB-05 WEB-06', browser='--browser', artifacts=('browser',), gaps=('Rich contenteditable exact verification is unsupported',)),
    'browser-offsets': suite('live_browser_offsets.py', 'EDIT-09 WEB-02 WEB-03', browser='--executable', artifacts=('browser-offset',)),
    'rich-editor-ime': suite('live_rich_ime.py', 'WEB-03 DATA-07', browser='--executable', artifacts=('rich-editor-ime',), gaps=('Owned ProseMirror native GTK simple IME only; no production adapter',)),
    'rich-editor-prototype': suite('live_rich_editor.py', 'WEB-03 DATA-07', browser='--executable', artifacts=('rich-editor',), gaps=('Test-only cooperating ProseMirror readback; no production adapter; exact serialization failures retained',)),
    'rich-copy': suite('live_rich_copy.py', 'WEB-03 CLIP-09', browser='--executable', artifacts=('rich-copy',), gaps=('Rich clipboard serialization and caret restoration lose information',)),
    'ime': suite('live_ime.py', 'EDIT-10', wm=False, artifacts=('ime',), gaps=('Generic backend cannot detect pending composition',)),
    'ime-browser': suite('live_ime_browser.py', 'EDIT-10', wm=False, browser='--executable', artifacts=('ime-browser',), gaps=('Browser preedit conflicts are not guarded',)),
    'accessibility-lifecycle': suite('live_accessibility_lifecycle.py', 'ENV-08 ENV-10 AX-01 FAULT-04', wm=False, artifacts=('accessibility-lifecycle',), gaps=('Existing GTK bridge does not reconnect after its bus is replaced',)),
    'mcp-reconnect': suite('live_mcp_reconnect.py', 'ENV-06 ENV-10 STATE-02', wm=False),
    'x11-isolation': suite('live_x11_isolation.py', 'FAULT-05 ERR-06', wm=False, modules=()),
    'window-tokens': suite('live_window_tokens.py', 'WIN-04', wm=False, modules=()),
    'window-metadata-capacity': suite('live_window_metadata_capacity.py', 'PERF-07', wm=False, modules=()),
    'window-metadata': suite('live_window_metadata.py', 'GEO-01 PERF-07 ERR-06'),
    'geometry': suite('live_geometry.py', 'OBS-02 GEO-01 GEO-02 GEO-04 GEO-09'),
    'clipboard-interference': suite('live_clipboard_interference.py', 'CLIP-01 CLIP-03 CLIP-04 CLIP-05 CLIP-06 CLIP-07 CONC-10 FAULT-08', artifacts=('clipboard',)),
    'drag': suite('live_drag.py', 'PTR-08'),
    'popup': suite('live_popup.py', 'MENU-04'),
    'resource-stress': suite('live_resource_stress.py', 'AX-06 PERF-06 PERF-09'),
    'application-launch': suite('live_application_launch.py', 'SEC-01 SEC-03 ERR-02 PERF-05 WM-09'),
    'application-services': suite('live_application_services.py', 'ERR-02 ERR-04 WM-09 WM-10'),
}


def private_environment(base, token):
    env = dict(os.environ, NO_AT_BRIDGE='0', GSETTINGS_BACKEND='memory', LUDA_ISOLATED_TEST_DISPLAY='1')
    for key, suffix in [('XDG_CONFIG_HOME', 'config'), ('XDG_DATA_HOME', 'data'),
                        ('XDG_CACHE_HOME', 'cache'), ('XDG_RUNTIME_DIR', 'runtime'),
                        ('GNUPGHOME', 'gnupg')]:
        path = base / suffix
        path.mkdir(mode=0o700)
        env[key] = str(path)
    env['XDG_CONFIG_DIRS'] = env['XDG_CONFIG_HOME']
    env['ICEAUTHORITY'] = str(base / 'iceauthority')
    for key in ('DISPLAY', 'XAUTHORITY', 'DBUS_SESSION_BUS_ADDRESS', 'DBUS_SESSION_BUS_PID',
                'SESSION_MANAGER', 'AT_SPI_BUS_ADDRESS', 'WAYLAND_DISPLAY', 'IBUS_ADDRESS',
                'GTK_IM_MODULE', 'QT_IM_MODULE', 'XMODIFIERS', 'DESKTOP_STARTUP_ID'):
        env.pop(key, None)
    env[TOKEN_KEY] = token
    return env


def owned_processes(token):
    """Find only this invocation's same-UID tagged descendants, including setsid."""
    marker = (TOKEN_KEY + '=' + token).encode()
    found = {}
    for directory in Path('/proc').iterdir():
        if not directory.name.isdigit():
            continue
        try:
            if directory.stat().st_uid != os.getuid() or marker not in (directory / 'environ').read_bytes().split(b'\0'):
                continue
            fields = (directory / 'stat').read_text().rsplit(')', 1)[1].split()
            if fields[0] != 'Z':
                found[int(directory.name)] = fields[19]
        except (OSError, IndexError):
            continue
    return found


def cleanup_owned(token):
    found = owned_processes(token)
    for sig in (signal.SIGTERM, signal.SIGKILL):
        for pid, start in found.items():
            if owned_processes(token).get(pid) == start:
                try:
                    os.kill(pid, sig)
                except ProcessLookupError:
                    pass
        deadline = time.monotonic() + .5
        while time.monotonic() < deadline and owned_processes(token):
            time.sleep(.02)
    return {'tagged_processes_found': len(found), 'survivors': sorted(owned_processes(token))}


def run_bounded(command, env, log, timeout, token):
    child = subprocess.Popen(command, env=env, cwd=ROOT, stdout=log, stderr=log, start_new_session=True)
    try:
        try:
            code = child.wait(timeout=timeout)
            result = {'status': 'passed' if code == 0 else 'failed', 'returncode': code}
        except subprocess.TimeoutExpired:
            result = {'status': 'timeout', 'returncode': None}
    finally:
        stop(child)
        cleanup = cleanup_owned(token)
    result['cleanup'] = cleanup
    if cleanup['survivors']:
        result['status'] = 'cleanup_failed'
    return result


def dependencies(spec, executable, electron=None, firefox=None):
    commands = ['xvfb-run', 'Xvfb', 'dbus-run-session', 'xfwm4', 'wmctrl', 'xdotool', 'scrot', 'xclip', 'xprop', 'gdbus']
    if spec['script'] in ('live_accessibility_lifecycle.py', 'live_mcp_reconnect.py'):
        commands.append('xfce4-session')
    commands.extend({'live_password_manager.py': ['keepassxc', 'keepassxc-cli'], 'live_tray.py': ['xfce4-panel'], 'live_tui.py': ['xterm'], 'live_dead_compose.py': ['setxkbmap', 'xkbcomp']}.get(spec['script'], ()))
    checks = {command: shutil.which(command) is not None for command in commands}
    imports = {'Gtk': "import gi;gi.require_version('Gtk','3.0');from gi.repository import Gtk",
               'Gtk4': "import gi;gi.require_version('Gtk','4.0');from gi.repository import Gtk",
               'Atspi': "import gi;gi.require_version('Atspi','2.0');from gi.repository import Atspi",
               'PyQt5': 'from PyQt5 import QtWidgets'}
    for module in spec['modules']:
        check = subprocess.run(['/usr/bin/python3', '-c', imports[module]], capture_output=True, text=True, timeout=5)
        checks['system_python:' + module] = check.returncode == 0
    if spec['browser_argument']:
        checks['browser_executable'] = bool(executable and Path(executable).is_file() and os.access(executable, os.X_OK))
    if spec.get('electron_argument'):
        checks['electron_executable'] = bool(electron and Path(electron).is_file() and os.access(electron, os.X_OK))
    if spec.get('firefox_argument'):
        checks['firefox_executable'] = bool(firefox and Path(firefox).is_file() and os.access(firefox, os.X_OK))
    return checks


def inside(name, executable, electron=None, firefox=None):
    spec = SUITES[name]
    wm = None
    try:
        if spec['runner_window_manager']:
            wm = subprocess.Popen(['xfwm4', '--compositor=off'])
            deadline = time.monotonic() + 10
            while subprocess.run(['wmctrl', '-m'], capture_output=True, timeout=2).returncode:
                if wm.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError('Private window manager not ready')
                time.sleep(.1)
        command = [sys.executable, str(ROOT / 'tests' / spec['script'])]
        if spec['browser_argument']:
            command.extend([spec['browser_argument'], executable])
        if spec.get('electron_argument'):
            command.extend([spec['electron_argument'], electron])
        if spec.get('firefox_argument'):
            command.extend([spec['firefox_argument'], firefox])
        return subprocess.call(command, cwd=ROOT)
    finally:
        if wm is not None:
            wm.terminate()
            try:
                wm.wait(timeout=3)
            except subprocess.TimeoutExpired:
                wm.kill(); wm.wait(timeout=2)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--list', action='store_true')
    group = parser.add_mutually_exclusive_group()
    group.add_argument('--all', action='store_true', help='Run every listed suite, including known failures.')
    group.add_argument('--suites', nargs='+', choices=SUITES)
    parser.add_argument('--executable', default=os.environ.get('LUDA_CHROMIUM_EXECUTABLE'), help='Chromium executable; also LUDA_CHROMIUM_EXECUTABLE.')
    parser.add_argument('--firefox-executable', default=os.environ.get('LUDA_FIREFOX_EXECUTABLE'), help='Separately provisioned test-only Firefox executable; also LUDA_FIREFOX_EXECUTABLE.')
    parser.add_argument('--electron-executable', default=os.environ.get('LUDA_ELECTRON_EXECUTABLE'), help='Separately installed test-only Electron executable.')
    parser.add_argument('--timeout', type=int, default=180, help='Per-suite watchdog seconds, 1..300.')
    parser.add_argument('--inside', choices=SUITES, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.list:
        print(json.dumps(SUITES, indent=2)); return 0
    if os.geteuid() == 0:
        parser.error('Run as an ordinary desktop user, never root.')
    if not 1 <= args.timeout <= 300:
        parser.error('--timeout must be 1..300 seconds')
    if args.inside:
        if os.environ.get('LUDA_ISOLATED_TEST_DISPLAY') != '1' or not os.environ.get(TOKEN_KEY):
            parser.error('--inside is reserved for the isolated runner')
        return inside(args.inside, args.executable, args.electron_executable, args.firefox_executable)
    selected = list(SUITES) if args.all else args.suites
    if not selected:
        parser.error('Explicitly choose --all or --suites; --list shows coverage.')
    output = ROOT / 'artifacts/qualification-matrix' / ('run-' + str(time.time_ns()))
    output.mkdir(parents=True)
    evidence = {'schema_version': 1, 'policy': 'Related IDs guide review; no result automatically qualifies requirements. Known failures remain failures.',
                'source_before': source_fingerprint(ROOT), 'environment': {'uid': os.getuid(), 'python': platform.python_version(),
                'architecture': platform.machine(), 'distribution': platform.freedesktop_os_release()}, 'suites': []}
    package = subprocess.run(['dpkg-query', '-W', 'xvfb', 'xfwm4', 'xfce4-session', 'python3-gi', 'python3-pyqt5', 'at-spi2-core', 'gir1.2-gtk-4.0'], capture_output=True, text=True, timeout=5)
    evidence['environment']['packages'] = package.stdout.splitlines()
    if args.executable:
        check = subprocess.run([args.executable, '--version'], capture_output=True, text=True, timeout=5) if Path(args.executable).is_file() and os.access(args.executable, os.X_OK) else None
        evidence['environment']['browser'] = {'executable': args.executable, 'version': check.stdout.strip() if check else 'unavailable'}
    try:
        for name in selected:
            spec = SUITES[name]; destination = output / name; destination.mkdir()
            began = time.monotonic(); since = time.time_ns()
            row = {'suite': name, 'related_requirements': spec['related_requirements'], 'known_gaps': spec['known_gaps'], 'source_before': source_fingerprint(ROOT)}
            try:
                row['dependencies'] = dependencies(spec, args.executable, args.electron_executable, args.firefox_executable)
                if not all(row['dependencies'].values()):
                    row.update(status='dependency_missing', returncode=None)
                else:
                    with tempfile.TemporaryDirectory(prefix='luda-matrix-') as directory:
                        token = uuid.uuid4().hex
                        env = private_environment(Path(directory), token)
                        command = ['xvfb-run', '-a', '-s', '-screen 0 1440x1000x24 -nolisten tcp',
                                   'dbus-run-session', '--', sys.executable, str(Path(__file__).resolve()), '--inside', name]
                        if args.executable:
                            command.extend(['--executable', args.executable])
                        if args.firefox_executable:
                            command.extend(['--firefox-executable', args.firefox_executable])
                        if args.electron_executable:
                            command.extend(['--electron-executable', args.electron_executable])
                        row['command'] = command
                        with (destination / 'suite.log').open('wb') as log:
                            row.update(run_bounded(command, env, log, args.timeout, token))
                for folder in spec['artifact_directories']:
                    for artifact in (ROOT / 'artifacts' / folder).rglob('*'):
                        if artifact.is_file() and not artifact.is_symlink() and artifact.stat().st_mtime_ns >= since:
                            target = destination / 'evidence' / artifact.relative_to(ROOT / 'artifacts')
                            target.parent.mkdir(parents=True, exist_ok=True)
                            shutil.copyfile(artifact, target)
            except Exception as exc:
                row.update(status='harness_error', error=type(exc).__name__ + ': ' + str(exc)[:500])
            row['seconds'] = round(time.monotonic() - began, 3)
            row['source_after'] = source_fingerprint(ROOT)
            row['source_unchanged'] = row['source_before'] == row['source_after']
            if not row['source_unchanged']:
                row['status'] = 'source_changed'
            evidence['suites'].append(row)
            (destination / 'result.json').write_text(json.dumps(row, indent=2) + '\n')
            print(json.dumps({key: row.get(key) for key in ('suite', 'status', 'returncode', 'seconds')}), flush=True)
    finally:
        evidence['source_after'] = source_fingerprint(ROOT)
        evidence['source_unchanged'] = evidence['source_before'] == evidence['source_after']
        (output / 'results.json').write_text(json.dumps(evidence, indent=2) + '\n')
    print('Results: ' + str(output / 'results.json'), flush=True)
    return 0 if evidence['source_unchanged'] and len(evidence['suites']) == len(selected) and all(row['status'] == 'passed' for row in evidence['suites']) else 1


if __name__ == '__main__':
    sys.exit(main())
