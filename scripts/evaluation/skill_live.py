#!/usr/bin/env python3
"""Fresh private XFCE confirmation; run only after both frozen benchmark gates.

Each invocation owns one ordinary-account Xvfb/DBus/HOME session. Independent
before/after evidence is retained; a recorded run still requires visual/semantic
adjudication and is never automatically labelled an acceptance pass.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
from qualification_matrix import cleanup_owned, private_environment, run_bounded
from agent_eval import stop

ACCEPTED_HASH = 'e90eae580e187882b7d6308eb35c77ff19a5a483857a5a0202a52ca7d6f88260'
BASELINE = 'eb268e820a9c96f2c934664b5edb18a0bd416c0a'
REFERENCES = {'setup.md', 'targeting.md', 'text.md', 'controls.md', 'workflows.md', 'recovery.md', 'optional.md'}


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def checked_skill(skill):
    files = [skill / 'SKILL.md', *sorted((skill / 'references').glob('*.md'))]
    if {p.name for p in files[1:]} != REFERENCES:
        raise ValueError('Require the seven original references')
    hashes = {str(p.relative_to(skill)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    if hashes['SKILL.md'] != ACCEPTED_HASH:
        raise ValueError('The installed entry skill must match the accepted artifact')
    for name in REFERENCES:
        original = subprocess.check_output(['git', '-C', str(ROOT), 'show', f'{BASELINE}:skills/luda/references/{name}'])
        if hashes[f'references/{name}'] != hashlib.sha256(original).hexdigest():
            raise ValueError(f'Reference differs from accepted baseline: {name}')
    return hashes


def check_child(base):
    if (os.geteuid() == 0 or os.environ.get('LUDA_ISOLATED_TEST_DISPLAY') != '1'
            or not os.environ.get('LUDA_MATRIX_PROCESS_TOKEN')
            or Path(os.environ.get('HOME', '')) != base / 'home'
            or os.environ.get('DISPLAY', '').split('.')[0] in ('', ':1')
            or os.environ.get('XDG_CONFIG_HOME') != str(base / 'config')):
        raise RuntimeError('Only an ordinary-account private desktop is allowed')


def oracle(desktop, app, base, name):
    """Read actual xfconf and AT-SPI independently of agent tool receipts."""
    theme = subprocess.check_output(['xfconf-query', '-c', 'xsettings', '-p', '/Net/ThemeName'], text=True, timeout=5).strip()
    code = '''import gi,json
 gi.require_version('Atspi','2.0')
 from gi.repository import Atspi
 rows=[]
 def walk(n):
  try:
   if n.get_state_set().contains(Atspi.StateType.SELECTED):rows.append({'name':n.get_name(),'role':n.get_role_name(),'pid':n.get_process_id()})
   for i in range(n.get_child_count()):walk(n.get_child_at_index(i))
  except Exception:pass
 walk(Atspi.get_desktop(0))
 print(json.dumps(rows))
'''
    # Remove the single formatting indent from the embedded standalone program.
    code = '\n'.join(line[1:] if line.startswith(' ') else line for line in code.splitlines())
    selected = json.loads(subprocess.check_output(['/usr/bin/python3', '-c', code], text=True, timeout=10))
    observation = desktop.observe(max_width=1280)
    png = base / f'{name}.png'
    png.write_bytes(base64.b64decode(observation.pop('image_base64')))
    windows = [w for w in observation['windows'] if w['pid'] == app.pid]
    selected = [n for n in selected if n['pid'] == app.pid]
    result = {'theme': theme, 'selected_nodes': selected, 'application_windows': windows,
              'screenshot_sha256': hashlib.sha256(png.read_bytes()).hexdigest(),
              'observation': observation, 'app_alive': app.poll() is None}
    write(base / f'{name}.json', result)
    return result


def child(base, timeout):
    check_child(base)
    from luda.desktop import Desktop
    children = []
    desktop = None
    try:
        subprocess.run(['xfconf-query', '-c', 'xsettings', '-p', '/Net/ThemeName', '--create', '--type', 'string', '--set', 'Greybird'], check=True, timeout=5)
        for command in (['xfwm4', '--compositor=off'], ['xfsettingsd', '--no-daemon']):
            children.append(subprocess.Popen(command))
        time.sleep(1)
        subprocess.run(['xsetroot', '-solid', '#202020'], check=True, timeout=5)
        app = subprocess.Popen(['xfce4-appearance-settings'])
        children.append(app)
        desktop = Desktop()
        deadline = time.monotonic() + 15
        while not any(w['pid'] == app.pid for w in desktop.list_windows()):
            if app.poll() is not None or time.monotonic() > deadline:
                raise RuntimeError('Appearance did not become visible')
            time.sleep(.1)
        time.sleep(.5)
        initial = oracle(desktop, app, base, 'initial')
        if initial['theme'] != 'Greybird' or not initial['application_windows']:
            raise RuntimeError('Initial light setting and visible page were not established')
        if not any(n['name'].splitlines()[0] == 'Greybird' for n in initial['selected_nodes'] if n['name']):
            raise RuntimeError('Initial theme selection was not independently established')
        keys = ('HOME', 'DISPLAY', 'DBUS_SESSION_BUS_ADDRESS', 'XAUTHORITY', 'XDG_RUNTIME_DIR',
                'XDG_CONFIG_HOME', 'XDG_DATA_HOME', 'XDG_CACHE_HOME', 'XDG_CONFIG_DIRS',
                'XDG_CURRENT_DESKTOP', 'LANG', 'LC_ALL', 'PATH', 'NO_AT_BRIDGE', 'GTK_MODULES',
                'LUDA_MATRIX_PROCESS_TOKEN', 'LUDA_ISOLATED_TEST_DISPLAY')
        write(base / 'ready.json', {k: os.environ[k] for k in keys if k in os.environ})
        deadline = time.monotonic() + timeout + 45
        while not (base / 'finish').exists():
            if time.monotonic() > deadline:
                raise TimeoutError('Agent/evaluator did not request final capture')
            time.sleep(.1)
        oracle(desktop, app, base, 'final')
    finally:
        if desktop:
            desktop.close()
        for process in reversed(children):
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=3)


def launch(base, themes, timeout):
    token = uuid.uuid4().hex
    env = private_environment(base, token)
    home = base / 'home'
    home.mkdir(mode=0o700)
    shutil.copytree(themes / 'themes', home / '.themes')
    env.update(HOME=str(home), XDG_CURRENT_DESKTOP='XFCE', LANG='C.UTF-8', LC_ALL='C.UTF-8', GTK_MODULES='gail:atk-bridge')
    for key in ('GTK_THEME', 'GTK2_RC_FILES'):
        env.pop(key, None)
    with (base / 'desktop.log').open('wb') as log:
        result = run_bounded(['xvfb-run', '-a', '-s', '-screen 0 1024x768x24 -nolisten tcp',
                              'dbus-run-session', '--', sys.executable, __file__, '--child', str(base),
                              '--timeout', str(timeout)], env, log, timeout + 80, token)
    write(base / 'cleanup.json', result)
    return 0 if result['status'] == 'passed' else 1


def wait_for(path, process, seconds):
    deadline = time.monotonic() + seconds
    while not path.exists():
        if process.poll() is not None or time.monotonic() > deadline:
            raise RuntimeError(f'Private desktop did not produce {path.name}')
        time.sleep(.1)


def server_command(user, env):
    # The isolated Codex workspace is deliberately unreadable to the GUI account.
    # FastMCP loads relative .env paths during import, so drop privilege only with
    # an explicit working directory inside the owned GUI profile.
    return ['/usr/sbin/runuser', '-u', user, '--', '/usr/bin/env', '--chdir=' + env['HOME'],
            *[f'{k}={v}' for k, v in env.items()], str(ROOT / '.venv/bin/luda')]


async def check_mcp(server, cwd, output):
    """Actual stdio handshake/list/doctor from an inaccessible inherited cwd."""
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    result = {'status': 'unassessable', 'argv': server,
              'inherited_cwd_mode': oct(cwd.stat().st_mode & 0o777)}
    async def exercise():
        with (output / 'mcp-preflight.stderr.log').open('w') as errors:
            async with stdio_client(StdioServerParameters(command=server[0], args=server[1:], cwd=str(cwd)), errlog=errors) as streams:
                async with ClientSession(*streams) as session:
                    initialized = await session.initialize()
                    listing = await session.list_tools()
                    result['initialize'] = initialized.model_dump(mode='json')
                    result['tools'] = [t.name for t in listing.tools]
                    if 'desktop_doctor' not in result['tools']:
                        raise RuntimeError('Actual MCP server does not advertise desktop_doctor')
                    doctor = await session.call_tool('desktop_doctor', {})
                    result['doctor_response'] = doctor.model_dump(mode='json')
                    texts = [c.text for c in doctor.content if c.type == 'text']
                    payload = json.loads(texts[0]) if texts else {}
                    if doctor.isError or payload.get('ready') is not True:
                        raise RuntimeError('Actual MCP desktop_doctor did not confirm readiness')
                    result['status'] = 'passed'
    try:
        await asyncio.wait_for(exercise(), timeout=30)
    except BaseException as exc:
        result['error'] = repr(exc)
        raise
    finally:
        write(output / 'mcp-preflight.json', result)
    return result


def recorded_status(interaction):
    if interaction.get('status') == 'recorded':
        return 'recorded_awaiting_review'
    if interaction.get('status') == 'timeout':
        return 'timeout'
    return 'unassessable'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--child', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--launch', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--themes', type=Path, required=False, help='Directory containing real themes/Greybird{,-dark}')
    parser.add_argument('--user', help='Explicit ordinary desktop account')
    parser.add_argument('--skill', type=Path, default=ROOT / 'skills/luda')
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts/skill-live')
    parser.add_argument('--timeout', type=int, default=240)
    parser.add_argument('--codex', default=shutil.which('codex') or 'codex')
    parser.add_argument('--auth-home', type=Path, default=Path(os.environ.get('CODEX_HOME', Path.home() / '.codex')))
    parser.add_argument('--prepare-only', action='store_true', help='Exercise private setup/oracles/cleanup without an evaluated agent')
    args = parser.parse_args()
    if not 1 <= args.timeout <= 600:
        parser.error('--timeout must be 1..600 seconds')
    if args.child:
        child(args.child, args.timeout)
        return 0
    if args.launch:
        return launch(args.launch, args.themes, args.timeout)
    if not args.user or pwd.getpwnam(args.user).pw_uid == 0:
        parser.error('--user must name an explicit ordinary account')
    if not args.themes or any(not (args.themes / 'themes' / t / 'gtk-3.0/gtk.css').is_file() for t in ('Greybird', 'Greybird-dark')):
        parser.error('--themes must provide real Greybird and Greybird-dark assets')
    account = pwd.getpwnam(args.user)
    hashes = checked_skill(args.skill)
    out = args.output.resolve() / (time.strftime('%Y%m%dT%H%M%SZ', time.gmtime()) + '-' + uuid.uuid4().hex)
    out.mkdir(parents=True, mode=0o700)
    result = {'status': 'preparing', 'acceptance': 'ungraded', 'prepare_only': args.prepare_only,
              'skill_hashes': hashes, 'runner_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'model': 'gpt-5.6-sol', 'reasoning_override': None, 'ordinary_account': args.user}
    launcher = None
    with tempfile.TemporaryDirectory(prefix='luda-live-confirmation-', dir='/workspace') as directory:
        base = Path(directory)
        base.chmod(0o755)
        desktop = base / 'desktop'
        desktop.mkdir()
        os.chown(desktop, account.pw_uid, account.pw_gid)
        try:
            with (out / 'launcher.log').open('wb') as log:
                launcher = subprocess.Popen(['runuser', '-u', args.user, '--', str(ROOT / '.venv/bin/python'), __file__,
                    '--launch', str(desktop), '--themes', str(args.themes.resolve()), '--timeout', str(args.timeout)],
                    stdout=log, stderr=log, start_new_session=True)
                wait_for(desktop / 'ready.json', launcher, 30)
                result['initial'] = json.loads((desktop / 'initial.json').read_text())
                env = json.loads((desktop / 'ready.json').read_text())
                server = server_command(args.user, env)
                hostile_cwd = base / 'agent-cwd-preflight'
                hostile_cwd.mkdir(mode=0o700)
                result['mcp_preflight'] = asyncio.run(check_mcp(server, hostile_cwd, out))
                if not args.prepare_only:
                    from skill_interactions import run_interaction
                    cli = subprocess.check_output([args.codex, '--version'], text=True, timeout=10).strip()
                    result['cli_version'] = cli
                    if cli != 'codex-cli 0.155.1':
                        raise RuntimeError(f'Expected recorded evaluation CLI 0.155.1; found {cli}')
                    result['interaction'] = run_interaction('live-theme', args.skill, out / 'agent', args.codex,
                        args.timeout, args.auth_home, server)
                    if result['interaction']['installed_skill_hashes'] != hashes:
                        raise RuntimeError('Installed skill hash mismatch')
                (desktop / 'finish').touch()
                wait_for(desktop / 'final.json', launcher, 20)
                result['final'] = json.loads((desktop / 'final.json').read_text())
                launcher.wait(timeout=15)
                if launcher.returncode != 0:
                    raise RuntimeError('Private desktop capture/cleanup failed')
                result['status'] = ('preflight_complete' if args.prepare_only else recorded_status(result['interaction']))
                result['review_required'] = 'Read final screenshot content and ordinary controls, visible Appearance page, selected/applied theme, agent post-effect observation and final claim; inspect all events/errors and GUI-only audit. Recorded is not passed.'
        except Exception as exc:
            result['status'] = 'failed'
            result['harness_error'] = str(exc)
        finally:
            (desktop / 'finish').touch()
            if launcher:
                try:
                    launcher.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    stop(launcher)
            if (desktop / 'ready.json').exists():
                token = json.loads((desktop / 'ready.json').read_text()).get('LUDA_MATRIX_PROCESS_TOKEN')
                if token:
                    result['final_cleanup'] = cleanup_owned(token)
                    if result['final_cleanup']['survivors']:
                        result['status'] = 'failed'
                        result['harness_error'] = 'Owned desktop processes survived cleanup'
            for name in ('initial.json', 'initial.png', 'final.json', 'final.png', 'desktop.log', 'cleanup.json'):
                if (desktop / name).is_file():
                    shutil.copyfile(desktop / name, out / name)
            result['artifact_hashes'] = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in out.iterdir() if p.is_file()}
            write(out / 'result.json', result)
    print(out)
    return 0 if result['status'] in ('preflight_complete', 'recorded_awaiting_review') else 1


if __name__ == '__main__':
    raise SystemExit(main())
