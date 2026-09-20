#!/usr/bin/env python3
"""Install Luda into an existing running Silo desktop and emit a reviewable bundle."""
import argparse
import json
import os
from pathlib import Path
import pwd
import re
import signal
import subprocess
import sys
import tempfile

from manage_install import checked_prefix, config, doctor, InstallError

SILO_HELPER = Path('/usr/local/bin/silo-desktop')


class BootstrapError(Exception):
    pass


def validate(source, prefix, output, user):
    prefix = checked_prefix(str(prefix))
    source, output = Path(source), Path(output)
    for label, path in [('source', source), ('output', output)]:
        if not path.is_absolute() or path.resolve() != path or any(ord(c) < 32 for c in str(path)) or '..' in path.parts:
            raise BootstrapError(f'{label} must be an absolute literal path without symlink components or traversal.')
    for file in ['scripts/install.sh', 'scripts/manage_install.py', 'requirements.lock', 'pyproject.toml', 'skills/luda/SKILL.md']:
        if not (source / file).is_file():
            raise BootstrapError('Trusted local source is missing required Luda files.')
    if output.exists() or output.is_symlink():
        raise BootstrapError('Output must be a fresh directory; existing content is never replaced.')
    if not output.parent.is_dir() or output.parent.stat().st_uid != os.getuid() or output.parent.stat().st_mode & 0o022:
        raise BootstrapError('Output parent must exist, belong to this account and not be writable by others.')
    if output == prefix or prefix in output.parents or output in prefix.parents or output == source or output in source.parents:
        raise BootstrapError('Output must not contain or overlap the installation prefix or source.')
    if not re.fullmatch(r'[a-z_][a-z0-9_-]*[$]?', user):
        raise BootstrapError('Desktop account must be a literal Linux account name.')
    try:
        account = pwd.getpwnam(user)
    except KeyError:
        raise BootstrapError('Desktop account does not exist.') from None
    if account.pw_uid == 0 or os.getuid() not in (0, account.pw_uid):
        raise BootstrapError('Run as root or the selected non-root desktop account.')
    return source, prefix, output


def run_process(argv, *, stdout, stderr, timeout):
    child = subprocess.Popen([str(v) for v in argv], stdout=stdout, stderr=stderr, start_new_session=True)
    try:
        return child.wait(timeout=timeout)
    finally:
        # Also reap descendants if their immediate parent has already exited.
        try:
            os.killpg(child.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            child.wait(timeout=2)
        except subprocess.TimeoutExpired:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait(timeout=2)
        try:
            os.killpg(child.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass


def desktop_status(user):
    if not SILO_HELPER.is_file():
        raise BootstrapError('Silo desktop helper is missing; install the desktop in Silo first.')
    with tempfile.TemporaryFile() as stream:
        code = run_process([SILO_HELPER, 'status'], stdout=stream, stderr=subprocess.DEVNULL, timeout=15)
        stream.seek(0)
        raw = stream.read(16385)
    if code or len(raw) > 16384:
        raise BootstrapError('Silo desktop status failed or exceeded its response limit.')
    try:
        value = json.loads(raw)
    except (ValueError, UnicodeError):
        raise BootstrapError('Silo desktop status is not valid JSON.') from None
    if not isinstance(value, dict) or value.get('version') != '1' or value.get('installed') is not True or value.get('user') != user:
        raise BootstrapError('Silo desktop status has an unsupported version, missing installation or different account.')
    if value.get('state') not in ('running', 'starting', 'stopped', 'failed'):
        raise BootstrapError('Silo desktop status has an unknown state.')
    # Never forward arbitrary fields, display strings, or helper stderr.
    return {'installed': True, 'version': '1', 'user': user, 'state': value['state']}


def bootstrap(source, prefix, output, user, skip_system=False):
    result = {'ok': False, 'stage': 'validation', 'installation_completed': False,
              'configuration_generated': False, 'settings_modified': False}
    try:
        source, prefix, output = validate(source, prefix, output, user)
        result['stage'] = 'desktop_preflight'
        result['desktop'] = desktop_status(user)
        if result['desktop']['state'] != 'running':
            raise BootstrapError('Desktop is not running. Start it explicitly in Silo, then retry.')
        output.mkdir(mode=0o700)
        result['output'] = str(output)
        result['stage'] = 'installation'
        command = ['bash', source / 'scripts/install.sh', prefix]
        if skip_system:
            command.append('--skip-system')
        if run_process(command, stdout=sys.stderr, stderr=sys.stderr, timeout=1800):
            raise BootstrapError('Installer failed; inspect stderr. Existing installer preservation rules apply.')
        result['installation_completed'] = True
        result['selected_release'] = (prefix / 'current').resolve().name
        result['stage'] = 'readiness'
        readiness = doctor(prefix, user)
        result['tools'] = {'ready': readiness.get('ready') is True}
        if not result['tools']['ready']:
            raise BootstrapError('Installed release is selected but tools are not ready.')
        result['stage'] = 'configuration'
        config(prefix, output / 'config', user, placement='remote')
        result.update(ok=True, stage='complete', configuration_generated=True,
                      config_directory=str(output / 'config'))
    except (BootstrapError, InstallError, OSError, ValueError, subprocess.TimeoutExpired) as exc:
        # Exceptions from a child/provider can contain arbitrary text: emit only
        # our stage-specific recovery instruction, never raw stdout/error text.
        result['error'] = {
            'validation': 'Check absolute source/prefix/output paths, ownership, account and source files; no installation attempted.',
            'desktop_preflight': 'Require compatible Silo status for the selected account and an explicitly running desktop; no installation attempted.',
            'installation': 'Installation did not complete; inspect installer stderr and selected release before retrying.',
            'readiness': 'Installation completed; selected release remains installed. Resolve session readiness, then retry with a fresh output directory.',
            'configuration': 'Installation completed; selected release remains installed. Resolve configuration output failure, then retry with a fresh output directory.',
        }[result['stage']]
        if isinstance(exc, BootstrapError):
            result['reason'] = str(exc)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', required=True, type=Path, help='Trusted local Luda source checkout')
    parser.add_argument('--prefix', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path, help='Fresh bundle directory beneath an owned existing parent')
    parser.add_argument('--user', required=True)
    parser.add_argument('--skip-system', action='store_true')
    args = parser.parse_args()
    result = bootstrap(args.source, args.prefix, args.output, args.user, args.skip_system)
    print(json.dumps(result, indent=2))
    return 0 if result['ok'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
