"""Configure Luda tools and skill together, without requiring a running desktop."""
from __future__ import annotations

import argparse
from contextlib import contextmanager
from dataclasses import dataclass
import fcntl
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import sys
import tempfile

from .setup_clients import CLIENTS, render_config

ALIASES = {'claude': 'claude-code', 'gemini': 'gemini-cli', 'copilot': 'copilot-cli'}


@dataclass
class Change:
    path: Path
    before: bytes | None
    after: bytes | None


def regular_path(path):
    """Do not write through symlinks, including directory components."""
    path = Path(path).absolute()
    if '..' in path.parts or any(ord(c) < 32 for c in str(path)):
        raise ValueError(f'Use a path without parent traversal or control characters: {path}')
    for item in (path, *path.parents):
        if item.is_symlink():
            raise ValueError(f'Refusing a symlink in setup destination: {item}. Use manual configuration instead.')
    return path


def read_file(path):
    regular_path(path)
    if path.exists():
        if not path.is_file():
            raise ValueError(f'Expected a regular file: {path}')
        return path.read_bytes()
    return None


def tree_files(path):
    regular_path(path)
    if not path.exists():
        return {}
    if not path.is_dir():
        raise ValueError(f'Expected a skill directory: {path}')
    result = {}
    for item in path.rglob('*'):
        regular_path(item)
        if item.is_file():
            result[str(item.relative_to(path))] = item.read_bytes()
        elif not item.is_dir():
            raise ValueError(f'Unsupported skill file: {item}')
    return result


def fingerprints(files):
    return {name: hashlib.sha256(data).hexdigest() for name, data in files.items()}


def atomic_write(path, data):
    regular_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if data is None:
        path.unlink(missing_ok=True)
        return
    previous_mode = path.stat().st_mode & 0o777 if path.exists() else 0o600
    fd, temporary = tempfile.mkstemp(prefix='.luda-setup-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temporary, previous_mode)
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def apply_changes(changes):
    """Preflight everything; roll back our writes if a later write fails."""
    changes = [c for c in changes if c.before != c.after]
    for change in changes:
        if read_file(change.path) != change.before:
            raise ValueError(f'File changed during setup; retry: {change.path}')
    applied = []
    try:
        for change in changes:
            if read_file(change.path) != change.before:
                raise ValueError(f'File changed during setup; retry: {change.path}')
            atomic_write(change.path, change.after)
            applied.append(change)
    except BaseException:
        for change in reversed(applied):
            # Never undo a concurrent editor's changes.
            if read_file(change.path) == change.after:
                atomic_write(change.path, change.before)
        raise
    return len(changes)


@contextmanager
def setup_lock(home):
    path = regular_path(home / '.local/state/luda/setup.lock')
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        os.close(fd)


def client_paths(client, home, scope, project=None, environ=None):
    environ = os.environ if environ is None else environ
    if scope == 'project':
        if not client.project_config or not client.project_skill:
            raise ValueError(f'{client.label} has no supported project setup; use --scope user or --export.')
        return project / client.project_config, project / client.project_skill / 'luda'
    config = home / client.config
    skill = home / client.skill / 'luda'
    if client.name == 'codex' and environ.get('CODEX_HOME'):
        base = Path(environ['CODEX_HOME'])
        if not base.is_absolute():
            raise ValueError('CODEX_HOME must be absolute.')
        config = base / 'config.toml'
    if client.name == 'copilot-cli' and environ.get('COPILOT_HOME'):
        base = Path(environ['COPILOT_HOME'])
        if not base.is_absolute():
            raise ValueError('COPILOT_HOME must be absolute.')
        config = base / 'mcp-config.json'
        skill = base / 'skills/luda'
    if environ.get('XDG_CONFIG_HOME'):
        base = Path(environ['XDG_CONFIG_HOME'])
        if not base.is_absolute():
            raise ValueError('XDG_CONFIG_HOME must be absolute.')
        if client.config.startswith('.config/'):
            config = base / client.config.removeprefix('.config/')
        if client.skill.startswith('.config/'):
            skill = base / client.skill.removeprefix('.config/') / 'luda'
    if client.name == 'opencode' and config.with_suffix('.jsonc').exists():
        if config.exists():
            raise ValueError('Both opencode.json and opencode.jsonc exist; use manual configuration to choose the active file.')
        config = config.with_suffix('.jsonc')
    return regular_path(config), regular_path(skill)


def plan_setup(names, home, source, command, *, scope='user', project=None, environ=None):
    expected = tree_files(source)
    if 'SKILL.md' not in expected:
        raise ValueError(f'Complete Luda skill missing: {source}')
    state_path = home / '.local/state/luda/setup.json'
    previous_state = read_file(state_path)
    state = json.loads(previous_state) if previous_state else {'version': 1, 'skills': {}}
    if not isinstance(state, dict) or state.get('version') != 1 or not isinstance(state.get('skills'), dict):
        raise ValueError(f'Unrecognized setup state: {state_path}')
    changes = {}
    destinations = []
    for name in names:
        client = CLIENTS[name]
        config, skill = client_paths(client, home, scope, project, environ)
        before = read_file(config)
        after = render_config(client, before, command[0], command[1:])
        changes[config] = Change(config, before, after)
        actual = tree_files(skill)
        if actual != expected and actual and state['skills'].get(str(skill)) != fingerprints(actual):
            raise ValueError(f'{skill} contains unmanaged or edited files. Move it to a backup before retrying; nothing was changed.')
        for relative in actual.keys() | expected.keys():
            target = skill / relative
            changes[target] = Change(target, actual.get(relative), expected.get(relative))
        state['skills'][str(skill)] = fingerprints(expected)
        destinations.append((client.label, config, skill))
    after_state = (json.dumps(state, indent=2, sort_keys=True) + '\n').encode()
    changes[state_path] = Change(state_path, previous_state, after_state)
    return list(changes.values()), destinations


def export_bundle(destination, source, command):
    destination = regular_path(destination)
    if destination.exists():
        raise ValueError('Export destination already exists; choose a new directory.')
    files = tree_files(source)
    if 'SKILL.md' not in files:
        raise ValueError('Complete Luda skill missing.')
    manifest = {'$schema': 'https://agent-plugins.org/schemas/1.0.0/plugin.schema.json',
                'name': 'luda', 'description': 'Linux desktop tools and skill'}
    mcp = {'mcpServers': {'luda': {'type': 'stdio', 'command': command[0], 'args': command[1:]}}}
    changes = [Change(destination / 'plugin.json', None, (json.dumps(manifest, indent=2) + '\n').encode()),
               Change(destination / 'mcp.json', None, (json.dumps(mcp, indent=2) + '\n').encode())]
    changes += [Change(destination / 'skills/luda' / name, None, data) for name, data in files.items()]
    apply_changes(changes)


def parser():
    p = argparse.ArgumentParser(description=__doc__, epilog='Run on the machine hosting the agent backend. For Codex SSH remote projects, that is the VM. This command never installs or authenticates the agent itself.')
    p.add_argument('--prefix', type=Path, default=Path('/opt/luda'), help='Managed runtime prefix (default: /opt/luda)')
    p.add_argument('--user', help='Agent and desktop account; root must select one explicitly')
    p.add_argument('--agent', action='append', default=[], help='Agent ID; repeat for several, or auto for detected clients. Use --list-agents.')
    p.add_argument('--scope', choices=['user', 'project'], default='user')
    p.add_argument('--project', type=Path, help='Absolute existing project directory for project scope')
    p.add_argument('--yes', action='store_true', help='Apply explicit choices without a confirmation prompt')
    p.add_argument('--list-agents', action='store_true', help='List supported adapters and exit')
    p.add_argument('--export', type=Path, help='Export a portable tools-and-skill plugin for custom clients to a new directory')
    p.add_argument('--session', choices=['discover', 'direct'], default='discover', help='discover attaches through luda-session (XFCE); direct inherits agent desktop environment')
    p.add_argument('--check-desktop', action='store_true', help='Also require a live desktop readiness check; omit while building images')
    p.add_argument('--validate-only', action='store_true', help=argparse.SUPPRESS)
    return p


def validate(args):
    prefix = args.prefix
    if not prefix.is_absolute() or len(prefix.parts) < 3 or '..' in prefix.parts or any(ord(c) < 32 for c in str(prefix)):
        raise ValueError('Use a dedicated absolute prefix, such as /opt/luda.')
    if os.getuid() == 0 and args.user is None:
        raise ValueError('Root must specify --user ACCOUNT (the agent and desktop account).')
    try:
        account = pwd.getpwnam(args.user) if args.user else pwd.getpwuid(os.getuid())
    except KeyError:
        raise ValueError('The selected Linux account does not exist. Create it before setup.') from None
    if os.getuid() not in (0, account.pw_uid):
        raise ValueError('Run as the selected account or root.')
    if not Path(account.pw_dir).is_absolute() or not Path(account.pw_dir).is_dir():
        raise ValueError('Selected account must have an existing absolute home directory.')
    if args.scope == 'project':
        if not args.project or not args.project.is_absolute() or not args.project.is_dir():
            raise ValueError('--scope project requires --project with an existing absolute directory.')
    elif args.project:
        raise ValueError('--project requires --scope project.')
    if args.export and args.agent:
        raise ValueError('Choose --export or --agent, not both.')
    if args.export:
        if not args.export.is_absolute():
            raise ValueError('--export requires an absolute path.')
        regular_path(args.export)
        if args.export.exists():
            raise ValueError('Export destination already exists; choose a new directory.')
    names = list(dict.fromkeys(ALIASES.get(name, name) for name in args.agent))
    unknown = set(names) - set(CLIENTS) - {'auto'}
    if unknown:
        raise ValueError('Unknown agent: ' + ', '.join(sorted(unknown)) + '. Run luda setup --list-agents, or use --export for a custom client.')
    if 'auto' in names and len(names) > 1:
        raise ValueError('Use --agent auto alone, or select explicit agent IDs.')
    for name in names:
        if name != 'auto':
            client_paths(CLIENTS[name], Path(account.pw_dir), args.scope, args.project, {})
    return account, names


def detect(home):
    return [name for name, client in CLIENTS.items()
            if shutil.which(client.executable) or client_paths(client, home, 'user')[0].exists()]


def choose_agents(home):
    detected = detect(home)
    print('Select one or more agents for this account (comma-separated IDs).')
    for name, client in CLIENTS.items():
        print(f'  {name:16} {client.label}' + (' [detected]' if name in detected else ''))
    print('For other clients, cancel and use --export /absolute/new/plugin-directory.')
    answer = input('Agents: ').strip()
    names = list(dict.fromkeys(ALIASES.get(n.strip(), n.strip()) for n in answer.split(',') if n.strip()))
    if not names or any(name not in CLIENTS for name in names):
        raise ValueError('Choose supported agent IDs, or use --export for a custom client.')
    return names


def main(argv=None):
    p = parser()
    args = p.parse_args(argv)
    if args.list_agents:
        for name, client in CLIENTS.items():
            print(f'{name:16} {client.label} (user' + (', project' if client.project_config and client.project_skill else '') + ')')
        print('Custom clients: --export /absolute/new/plugin-directory')
        return
    try:
        account, names = validate(args)
        if args.validate_only:
            return
        # Account files are always written as their owner, including image builds.
        if os.getuid() == 0 and account.pw_uid != 0:
            os.initgroups(account.pw_name, account.pw_gid)
            os.setgid(account.pw_gid)
            os.setuid(account.pw_uid)
            os.environ.clear()
            os.environ.update(HOME=account.pw_dir, USER=account.pw_name, LOGNAME=account.pw_name,
                              PATH='/usr/local/bin:/usr/bin:/bin', LANG='C.UTF-8')
            os.chdir(account.pw_dir)
        home = Path(account.pw_dir)
        runtime = args.prefix / 'current/.venv/bin/luda'
        launcher = args.prefix / 'current/.venv/bin/luda-session'
        source = (args.prefix / 'current/skills/luda').resolve()
        for path in (runtime, launcher):
            if not path.is_file() or not os.access(path, os.X_OK):
                raise ValueError(f'Managed runtime missing or inaccessible: {path}. Run scripts/install.sh first, or select its --prefix.')
        command = [str(runtime)] if args.session == 'direct' else [str(launcher), '--user', account.pw_name, '--', str(runtime)]
        if names == ['auto']:
            names = detect(home)
            if not names:
                raise ValueError('No agents detected. Select --agent explicitly (works before the agent is installed), or use --export.')
        if not names and not args.export:
            if not sys.stdin.isatty():
                raise ValueError('Noninteractive setup requires --agent ID (repeatable), --agent auto, or --export PATH.')
            names = choose_agents(home)
        subprocess.run([str(runtime), '--version'], check=True, timeout=20, stdout=subprocess.DEVNULL)
        with setup_lock(home):
            if args.export:
                print(f'Export tools and skill to {args.export}')
                changes, destinations = [], []
            else:
                changes, destinations = plan_setup(names, home, source, command, scope=args.scope, project=args.project)
                for label, config, skill in destinations:
                    print(f'{label}:\n  Tools: {config}\n  Skill: {skill}')
            if not args.yes:
                if not sys.stdin.isatty():
                    raise ValueError('Review the destinations above, then rerun with --yes for noninteractive setup.')
                if input('Apply this setup? [y/N] ').strip().lower() not in ('y', 'yes'):
                    print('Cancelled; no agent configuration changed.')
                    return
            if args.export:
                export_bundle(args.export, source, command)
            else:
                count = apply_changes(changes)
                print(f'Configured tools and skill ({count} files changed).')
        print('Configuration prepared. Restart/reconnect the selected agent, then ask it to use Luda to inspect the desktop.')
        if args.export:
            print('Import this plugin with a compatible client, or use its mcp.json and skills/luda with your custom agent. Its command runs on this Linux machine.')
        if args.check_desktop:
            print('Checking the live desktop...')
            subprocess.run([*command, 'doctor'], check=True, timeout=35)
            print('Desktop readiness check passed. Tool and skill discovery inside the agent still needs its first connection.')
        else:
            print('Live desktop not checked (image builds need no running GUI). After starting the desktop, check with:')
            import shlex
            print('  ' + shlex.join([*command, 'doctor']))
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        p.exit(1, f'Setup failed: {exc}\n')


if __name__ == '__main__':
    main()
