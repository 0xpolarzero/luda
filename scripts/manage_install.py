#!/usr/bin/env python3
"""Versioned local installation and explicit agent configuration bundles."""
import argparse
from contextlib import contextmanager
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import tomllib
import uuid

ROOT = Path(__file__).resolve().parents[1]
MARKER = '.luda-install.json'


class InstallError(Exception):
    pass


def checked_prefix(value):
    path = Path(value)
    if not path.is_absolute() or path == Path('/') or len(path.parts) < 3:
        raise InstallError('Use a dedicated absolute prefix such as /opt/luda; system roots are refused.')
    if any(ord(c) < 32 for c in str(path)) or '..' in path.parts or path.resolve() != path:
        raise InstallError('Prefix cannot contain control characters, parent traversal or symlink components.')
    if path.exists() and (not path.is_dir() or path.stat().st_uid != os.getuid() or path.stat().st_mode & 0o022):
        raise InstallError('Existing prefix must be a directory owned by this account and not group/world writable.')
    return path


def atomic_json(path, value):
    temporary = path.with_name('.' + path.name + '.' + uuid.uuid4().hex)
    try:
        with temporary.open('x') as stream:
            json.dump(value, stream, indent=2)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


@contextmanager
def locked(prefix):
    prefix.mkdir(parents=True, exist_ok=True)
    fd = os.open(prefix / '.luda-install.lock', os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        yield
    except BlockingIOError as exc:
        raise InstallError('Another installation operation is running.') from exc
    finally:
        os.close(fd)


def state(prefix):
    marker = prefix / MARKER
    if marker.is_symlink():
        raise InstallError('Installation marker cannot be a symlink.')
    if not marker.exists():
        return {'product': 'luda', 'schema_version': 1, 'releases': []}
    try:
        value = json.loads(marker.read_text())
    except (OSError, ValueError) as exc:
        raise InstallError('Installation marker is unreadable; refusing to modify it.') from exc
    if value.get('product') != 'luda' or value.get('schema_version') != 1 or not isinstance(value.get('releases'), list):
        raise InstallError('Unrecognized installation marker.')
    if any(not isinstance(r, str) or not re.fullmatch(r'[A-Za-z0-9_.+-]+-[a-f0-9]{16}', r) for r in value['releases']):
        raise InstallError('Invalid release identity in installation marker.')
    return value


def invoke(argv, timeout=300):
    try:
        child = subprocess.Popen([str(a) for a in argv], start_new_session=True)
    except FileNotFoundError as exc:
        raise InstallError(f'Missing dependency: {argv[0]}') from exc
    try:
        code = child.wait(timeout=timeout)
        if code:
            raise InstallError(f'Installation command failed: {Path(argv[0]).name}; previous release remains selected.')
    except BaseException as exc:
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        child.wait(timeout=5)
        if isinstance(exc, subprocess.TimeoutExpired):
            raise InstallError(f'Installation command timed out: {Path(argv[0]).name}; previous release remains selected.') from exc
        raise


def release_identity(source):
    metadata = tomllib.loads((source / 'pyproject.toml').read_text())
    version = metadata['project']['version']
    if not re.fullmatch(r'[A-Za-z0-9_.+-]+', version):
        raise InstallError('Package version is not a safe release name.')
    files = [source / p for p in ('pyproject.toml', 'MANIFEST.in', 'requirements.lock', 'build-requirements.lock')]
    files += [source / name for name in ('.mcp.json', 'README.md', 'build-requirements.in') if (source / name).is_file()]
    files += [p for name in ('src', 'skills', 'scripts', 'docs', 'tests', '.codex-plugin') for p in (source / name).rglob('*')
              if p.is_file() and '__pycache__' not in p.parts and not any(part.endswith('.egg-info') for part in p.parts)]
    digest = hashlib.sha256()
    for path in sorted(files):
        digest.update(str(path.relative_to(source)).encode() + b'\0' + path.read_bytes() + b'\0')
    return version + '-' + digest.hexdigest()[:16]


def select(prefix, release):
    current = prefix / 'current'
    if current.exists() and not current.is_symlink():
        raise InstallError('Refusing to replace an unmanaged current path.')
    temporary = prefix / ('.current-' + uuid.uuid4().hex)
    try:
        temporary.symlink_to(Path('releases') / release)
        os.replace(temporary, current)
    finally:
        temporary.unlink(missing_ok=True)


def install(prefix, source, runner=invoke):
    identity = release_identity(source)
    with locked(prefix):
        metadata = state(prefix)
        releases = prefix / 'releases'
        if releases.is_symlink() or (releases.exists() and not (prefix / MARKER).exists()):
            raise InstallError('Existing releases path is not managed by this installer.')
        current = prefix / 'current'
        if current.is_symlink() and str(current.readlink()) not in [str(Path('releases') / r) for r in metadata['releases']]:
            raise InstallError('Existing current symlink is not managed by this installer.')
        if current.exists() and not current.is_symlink():
            raise InstallError('Existing current path is not managed by this installer.')
        if not (prefix / MARKER).exists():
            atomic_json(prefix / MARKER, metadata)
        releases.mkdir(exist_ok=True)
        release = releases / identity
        if release.exists() or release.is_symlink():
            if identity in metadata['releases'] and not release.is_symlink() and (release / 'release.json').is_file():
                verify_release(release, identity)
                select(prefix, identity)
                return {'status': 'already_installed', 'release': identity, 'prefix': str(prefix)}
            pending = release / '.luda-release-owner.json'
            if release.is_symlink() or not pending.is_file() or json.loads(pending.read_text()) != {'product': 'luda', 'release': identity}:
                raise InstallError('Release directory exists without a completed managed installation.')
            # A killed installer cannot run finally. Preserve its incomplete
            # directory for inspection and retry at the original final path.
            release.rename(releases / ('.interrupted-' + identity + '-' + uuid.uuid4().hex))
            metadata['releases'] = [r for r in metadata['releases'] if r != identity]
            atomic_json(prefix / MARKER, metadata)
        release.mkdir()
        try:
            atomic_json(release / '.luda-release-owner.json', {'product': 'luda', 'release': identity})
            # Build at the final path: moving a venv breaks absolute shebangs.
            runner([sys.executable, '-m', 'venv', release / '.venv'])
            python = release / '.venv/bin/python'
            runner([python, '-m', 'pip', 'install', '--require-hashes', '-r', source / 'requirements.lock'])
            runner([python, '-m', 'pip', 'install', '--require-hashes', '-r', source / 'build-requirements.lock'])
            runner([python, '-m', 'pip', 'wheel', '--no-build-isolation', '--no-deps', '--wheel-dir', release / 'wheels', source])
            wheels = list((release / 'wheels').glob('luda-*.whl'))
            if len(wheels) != 1:
                raise InstallError('Build did not produce exactly one Luda wheel.')
            runner([python, '-m', 'pip', 'install', '--no-deps', wheels[0]])
            runner([python, '-c', 'import luda.server; from importlib.metadata import version; print("Installed Luda", version("luda"))'])
            shutil.copytree(source / 'skills/luda', release / 'skills/luda')
            if release_identity(source) != identity:
                raise InstallError('Source changed during installation; previous release remains selected. Retry from an unchanged checkout.')
            atomic_json(release / 'release.json', {'product': 'luda', 'release': identity,
                        'wheel_sha256': hashlib.sha256(wheels[0].read_bytes()).hexdigest(),
                        'files': inventory(release)})
            metadata['releases'].append(identity)
            atomic_json(prefix / MARKER, metadata)
            select(prefix, identity)
        except BaseException:
            # Selection is the final step; interrupted preparation never replaces current.
            if identity not in state(prefix)['releases']:
                shutil.rmtree(release)
            raise
        return {'status': 'installed', 'release': identity, 'prefix': str(prefix)}


def rollback(prefix, release):
    with locked(prefix):
        metadata = state(prefix)
        if release not in metadata['releases'] or (prefix / 'releases').is_symlink() or (prefix / 'releases' / release).is_symlink() or not (prefix / 'releases' / release / 'release.json').is_file():
            raise InstallError('Requested release is not a completed managed installation.')
        verify_release(prefix / 'releases' / release, release)
        select(prefix, release)
        return {'status': 'selected', 'release': release}


def verify_release(directory, identity):
    """Verify owned payloads before reusing a completed release; preserve edits."""
    manifest = directory / 'release.json'
    try:
        if manifest.is_symlink():
            raise InstallError('Release manifest became a symlink; refusing selection.')
        value = json.loads(manifest.read_text())
        files = value.get('files')
        if value.get('product') != 'luda' or value.get('release') != identity or not isinstance(files, dict) or not files:
            raise InstallError('Invalid completed release manifest; refusing selection.')
        for name, expected in files.items():
            relative = Path(name)
            if relative.is_absolute() or '..' in relative.parts or not relative.parts:
                raise InstallError('Invalid completed release file path.')
            # CPython may refresh bytecode after installation; source files remain verified.
            if '__pycache__' in relative.parts or relative.suffix in ('.pyc', '.pyo'):
                continue
            path = directory / relative
            if any(parent.is_symlink() for parent in path.parents if parent != directory and directory in parent.parents):
                raise InstallError('Installed payload parent became a symlink; refusing selection.')
            actual = {'link': str(path.readlink())} if path.is_symlink() else {'sha256': hashlib.sha256(path.read_bytes()).hexdigest()} if path.is_file() else None
            if actual != expected:
                raise InstallError('Installed release files changed or disappeared; refusing selection and preserving those files.')
    except (OSError, ValueError, TypeError, AttributeError) as exc:
        raise InstallError('Completed release is unreadable; refusing selection.') from exc


def inventory(directory):
    files = {}
    for path in directory.rglob('*'):
        if path.is_symlink():
            files[str(path.relative_to(directory))] = {'link': str(path.readlink())}
        elif path.is_file():
            files[str(path.relative_to(directory))] = {'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}
    return files


def uninstall(prefix):
    if not prefix.exists():
        return {'status': 'not_installed'}
    with locked(prefix):
        metadata = state(prefix)
        if not (prefix / MARKER).exists():
            return {'status': 'not_installed'}
        plans = []
        for name in metadata['releases']:
            release = prefix / 'releases' / name
            if release.is_symlink() or (prefix / 'releases').is_symlink():
                raise InstallError('Managed release path became a symlink; refusing uninstall.')
            manifest = release / 'release.json'
            if not manifest.exists():
                continue
            value = json.loads(manifest.read_text())
            files = value.get('files', {})
            if value.get('product') != 'luda' or value.get('release') != name or not isinstance(files, dict):
                raise InstallError('Invalid release manifest; refusing uninstall.')
            if any(Path(f).is_absolute() or '..' in Path(f).parts for f in files):
                raise InstallError('Unsafe file path in release manifest.')
            plans.append((name, release, files))
        current = prefix / 'current'
        if current.is_symlink() and str(current.readlink()) in [str(Path('releases') / r) for r in metadata['releases']]:
            current.unlink()
        retained = []
        for name, release, files in plans:
            for relative, expected in files.items():
                path = release / relative
                if any(parent.is_symlink() for parent in path.parents if parent != release and release in parent.parents):
                    continue
                if path.is_symlink():
                    if expected == {'link': str(path.readlink())}:
                        path.unlink()
                elif path.is_file() and expected == {'sha256': hashlib.sha256(path.read_bytes()).hexdigest()}:
                    path.unlink()
            # The installer owns this manifest. Unknown/modified files remain.
            (release / 'release.json').unlink()
            for directory in sorted((p for p in release.rglob('*') if p.is_dir() and not p.is_symlink()), key=lambda p: len(p.parts), reverse=True):
                try:
                    directory.rmdir()
                except OSError:
                    pass
            try:
                release.rmdir()
            except OSError:
                atomic_json(release / '.luda-release-owner.json', {'product': 'luda', 'release': name})
                retained.append(name)
        metadata['releases'] = retained
        atomic_json(prefix / MARKER, metadata)
        return {'status': 'uninstalled', 'retained_modified_releases': retained,
                'note': 'Unmodified installed files removed; modified/unknown files and external configuration preserved.'}


def config(prefix, output, user, tool_approval="auto", placement="local"):
    if tool_approval not in ("auto","prompt","writes","approve") or placement not in ("local","remote"):
        raise InstallError("Unknown tool approval mode or MCP placement.")
    if not re.fullmatch(r'[a-z_][a-z0-9_-]*[$]?', user):
        raise InstallError('Desktop user must be a literal Linux account name.')
    metadata = state(prefix)
    if not (prefix / 'current').is_symlink() or not metadata['releases']:
        raise InstallError('Install and select a release before generating configuration.')
    if output.exists() or output.is_symlink():
        raise InstallError('Configuration output already exists; choose a new directory. Existing configuration is never overwritten.')
    output.mkdir(parents=True)
    try:
        command = str(prefix / 'current/.venv/bin/luda-session')
        arguments = ['--user', user, '--', str(prefix / 'current/.venv/bin/luda')]
        toml = '[mcp_servers.luda]\ncommand = ' + json.dumps(command) + '\nargs = ' + json.dumps(arguments) + '\nstartup_timeout_sec = 20\ntool_timeout_sec = 20\n'
        toml += "required = true\ndefault_tools_approval_mode = " + json.dumps(tool_approval) + "\n"
        if placement == "remote":
            toml += 'experimental_environment = "remote"\n'
        tomllib.loads(toml)
        (output / 'config.toml.fragment').write_text(toml)
        shutil.copytree(prefix / 'current/skills/luda', output / '.agents/skills/luda')
        (output / 'README.txt').write_text('Review config.toml.fragment and merge its [mcp_servers.luda] table into the Codex configuration used by the guest connection. Copy .agents/skills/luda into the guest workspace .agents/skills or the agent account ~/.agents/skills. Restart/reconnect Codex and verify desktop_doctor, desktop_observe and the Luda skill. Do not place guest executable paths into a host-local MCP process configuration. No existing configuration has been modified.\n')
    except BaseException:
        shutil.rmtree(output)
        raise
    return {'status': 'generated', 'output': str(output), 'desktop_user': user, 'tool_approval':tool_approval, 'placement':placement}


def doctor(prefix, user):
    release = prefix / 'current'
    if not release.is_dir():
        raise InstallError('No selected installation; run install or rollback first.')
    command = [release / '.venv/bin/luda-session', '--user', user, '--', release / '.venv/bin/python', '-c',
               'import json;from luda.desktop import Desktop;d=Desktop();r=d.doctor();d.close();print(json.dumps(r));raise SystemExit(0 if r["ready"] else 1)']
    result = subprocess.run([str(a) for a in command], capture_output=True, text=True, timeout=20)
    if result.returncode:
        raise InstallError('Desktop readiness failed: ' + (result.stdout or result.stderr)[-1500:])
    return json.loads(result.stdout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['install', 'uninstall', 'rollback', 'config', 'doctor'])
    parser.add_argument('--prefix', required=True)
    parser.add_argument('--source', type=Path, default=ROOT)
    parser.add_argument('--release')
    parser.add_argument('--output', type=Path)
    parser.add_argument('--user', default='silo-desktop')
    parser.add_argument('--tool-approval',choices=['auto','prompt','writes','approve'],default='auto',help='MCP tool approval policy in generated config; approve supports unattended sandbox tasks.')
    parser.add_argument('--placement',choices=['local','remote'],default='local',help='Use remote for a host Codex config targeting its selected SSH executor; local for Codex running inside the guest.')
    args = parser.parse_args()
    try:
        prefix = checked_prefix(args.prefix)
        if args.action == 'install':
            result = install(prefix, args.source.resolve())
        elif args.action == 'uninstall':
            result = uninstall(prefix)
        elif args.action == 'rollback':
            result = rollback(prefix, args.release)
        elif args.action == 'config':
            if args.output is None:
                parser.error('config requires --output')
            result = config(prefix, args.output, args.user, args.tool_approval, args.placement)
        else:
            result = doctor(prefix, args.user)
        print(json.dumps(result, indent=2))
    except (InstallError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        print(json.dumps({'ok': False, 'error': str(exc)}), file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
