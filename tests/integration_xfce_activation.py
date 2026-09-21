"""XFCE selection is not activation; verify the actual setting independently.

Run as an ordinary account: .venv/bin/python tests/integration_xfce_activation.py
Requires xfce4-settings, xfconf, xfwm4, Xvfb and AT-SPI. Creates its own display,
bus, profile and two minimal GTK themes; never changes the user's desktop.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from qualification_matrix import private_environment, run_bounded

BEFORE = 'Luda-Test-A'
AFTER = 'Luda-Test-B'


def setting():
    return subprocess.run(['xfconf-query', '-c', 'xsettings', '-p', '/Net/ThemeName'],
                          check=True, capture_output=True, text=True, timeout=3).stdout.strip()


def child(output):
    from luda.desktop import Desktop
    # Minimal real themes exercise the installed Appearance program's callbacks.
    for name in (BEFORE, AFTER):
        theme = Path(os.environ['HOME']) / '.themes' / name / 'gtk-3.0'
        theme.mkdir(parents=True)
        (theme / 'gtk.css').write_text('/* Disposable selection/activation test theme. */\n')
    subprocess.run(['xfconf-query', '-c', 'xsettings', '-p', '/Net/ThemeName',
                    '--create', '--type', 'string', '--set', BEFORE], check=True, timeout=3)
    children = []
    desktop = None
    evidence = {'before': setting()}
    try:
        children.append(subprocess.Popen(['xfwm4', '--compositor=off']))
        children.append(subprocess.Popen(['xfce4-appearance-settings']))
        desktop = Desktop()
        deadline = time.monotonic() + 10
        while True:
            windows = [w for w in desktop.list_windows() if w['pid'] == children[-1].pid]
            if len(windows) == 1:
                break
            assert time.monotonic() < deadline, 'Appearance window unavailable'
            time.sleep(.1)
        window = windows[0]['window_id']
        desktop.activate(window)

        def row():
            nodes = desktop.inspect(window, name=AFTER)['nodes']
            matches = [n for n in nodes if n['name'].splitlines()[0] == AFTER and n['role'] == 'table cell']
            assert len(matches) == 1, nodes
            return matches[0]

        target = row()
        evidence['advertised_actions'] = target['actions']
        assert 'activate' in target['actions'], target
        evidence['choose'] = desktop.element(target['element_id'], 'choose')
        assert evidence['choose'].get('effect') == 'verified', evidence
        assert evidence['choose'].get('selected') is True, evidence
        target = row()  # Fresh inspection verifies row state, not task completion.
        evidence['selected_states'] = target['states']
        assert 'selected' in target['states'], target
        # An independent application oracle catches the original false success.
        time.sleep(.3)
        evidence['after_choose'] = setting()
        assert evidence['after_choose'] == BEFORE, evidence
        evidence['invoke'] = desktop.element(target['element_id'], 'invoke', action='activate')
        deadline = time.monotonic() + 3
        while setting() != AFTER and time.monotonic() < deadline:
            time.sleep(.05)
        evidence['after_activate'] = setting()
        assert evidence['after_activate'] == AFTER, evidence
        evidence['passed'] = True
    finally:
        if desktop is not None:
            desktop.close()
        for process in reversed(children):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)
        (output / 'result.json').write_text(json.dumps(evidence, indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--child', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if os.geteuid() == 0:
        parser.error('Run under an explicit ordinary test account, not root.')
    output = (args.output or ROOT / 'artifacts/xfce-activation' / str(time.time_ns())).resolve()
    output.mkdir(parents=True, exist_ok=True)
    if args.child:
        home = Path(os.environ.get('HOME', ''))
        if (os.environ.get('LUDA_ISOLATED_TEST_DISPLAY') != '1'
                or not os.environ.get('LUDA_MATRIX_PROCESS_TOKEN')
                or not home.parent.name.startswith('luda-xfce-activation-')
                or os.environ.get('XDG_CONFIG_HOME') != str(home.parent / 'config')):
            parser.error('Internal child requires the isolated runner environment.')
        return child(output)
    with tempfile.TemporaryDirectory(prefix='luda-xfce-activation-') as temporary:
        base = Path(temporary)
        token = uuid.uuid4().hex
        env = private_environment(base, token)
        home = base / 'home'
        home.mkdir()
        env.update(HOME=str(home), XDG_CURRENT_DESKTOP='XFCE', LANG='C.UTF-8', LC_ALL='C.UTF-8',
                   GTK_MODULES='gail:atk-bridge')
        for key in ('GTK_THEME', 'GTK2_RC_FILES'):
            env.pop(key, None)
        with (output / 'desktop.log').open('wb') as log:
            result = run_bounded(['xvfb-run', '-a', '-s', '-screen 0 1200x900x24 -nolisten tcp',
                                  'dbus-run-session', '--', sys.executable, __file__,
                                  '--child', '--output', str(output)], env, log, 45, token)
    (output / 'runner.json').write_text(json.dumps(result, indent=2) + '\n')
    print(output, result['status'])
    return 0 if result['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
