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
import time
import uuid

from manage_install import checked_prefix, config, doctor, InstallError, locked, release_identity

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
    if any(a == other or a in other.parents or other in a.parents
           for a, other in ((output, prefix), (output, source), (prefix, source))):
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


PROCESS_TOKEN = 'LUDA_BOOTSTRAP_PROCESS_TOKEN'


class InterruptedProcess(BootstrapError):
    def __init__(self, cleanup_verified):
        self.cleanup_verified = cleanup_verified
        super().__init__('Child execution interrupted; installation outcome must be inspected before retry.')


def process_identity(directory):
    stat = (directory / 'stat').read_text().rsplit(')', 1)[1].split()
    if stat[0] == 'Z':
        return None
    # Nondumpable processes can change /proc directory ownership to root;
    # the status Uid field remains the process identity, not that directory UID.
    uid = next(line for line in (directory / 'status').read_text().splitlines() if line.startswith('Uid:'))
    return (int(uid.split()[2]), stat[19])


def process_snapshot():
    result = {}
    for directory in Path('/proc').iterdir():
        if directory.name.isdigit():
            try:
                identity = process_identity(directory)
                if identity is not None:
                    result[int(directory.name)] = identity
            except (OSError, ValueError, IndexError, StopIteration):
                continue
    return result


def unreadable_new_candidates(baseline):
    for pid, identity in process_snapshot().items():
        if baseline.get(pid) == identity or (os.getuid() != 0 and identity[0] != os.getuid()):
            continue
        try:
            (Path('/proc') / str(pid) / 'environ').read_bytes()
        except (FileNotFoundError, ProcessLookupError):
            continue
        except OSError:
            # Candidate attribution is unknown. Do not signal it; refuse proof.
            return True
    return False


def tagged_processes(token):
    marker = (PROCESS_TOKEN + '=' + token).encode()
    found = {}
    for directory in Path('/proc').iterdir():
        if not directory.name.isdigit():
            continue
        try:
            if marker not in (directory / 'environ').read_bytes().split(b'\0'):
                continue
            identity = process_identity(directory)
            if identity is not None:
                found[int(directory.name)] = identity
        except (OSError, ValueError, IndexError, StopIteration):
            continue
    return found


def cleanup_tagged(token):
    for sig, duration in ((signal.SIGTERM, .3), (signal.SIGKILL, 1)):
        deadline = time.monotonic() + duration
        while True:
            found = tagged_processes(token)
            if not found:
                return True
            for pid, identity in found.items():
                if tagged_processes(token).get(pid) == identity:
                    try:
                        os.kill(pid, sig)
                    except ProcessLookupError:
                        pass
                    except PermissionError:
                        return False
            if time.monotonic() >= deadline:
                break
            time.sleep(.02)
    return not tagged_processes(token)


def run_process(argv, *, stdout, stderr, timeout):
    token = uuid.uuid4().hex
    baseline = process_snapshot()
    child = subprocess.Popen([str(v) for v in argv], stdout=stdout, stderr=stderr,
                             env={**os.environ, PROCESS_TOKEN: token}, start_new_session=True)
    interrupted = False
    code = None
    try:
        code = child.wait(timeout=timeout)
    except (subprocess.TimeoutExpired, KeyboardInterrupt):
        interrupted = True
    finally:
        clean = cleanup_tagged(token)
        if child.poll() is None:
            child.kill()
        child.wait(timeout=2)
        clean = clean and not unreadable_new_candidates(baseline)
    if interrupted or not clean:
        raise InterruptedProcess(clean)
    return code


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
              'configuration_generated': False, 'codex_settings_modified': False}
    try:
        source, prefix, output = validate(source, prefix, output, user)
        if os.getuid() != 0 and not skip_system:
            raise BootstrapError('System provisioning requires root; use --skip-system only after provisioning dependencies.')
        expected_release = release_identity(source)
        result['stage'] = 'desktop_preflight'
        result['desktop'] = desktop_status(user)
        if result['desktop']['state'] != 'running':
            raise BootstrapError('Desktop is not running. Start it explicitly in Silo, then retry.')
        output.mkdir(mode=0o700)
        result['output'] = str(output)
        result['stage'] = 'installation'
        result['installation_completed'] = None
        command = ['bash', source / 'scripts/install.sh', prefix]
        if skip_system:
            command.append('--skip-system')
        if run_process(command, stdout=sys.stderr, stderr=sys.stderr, timeout=1800):
            raise BootstrapError('Installer failed; inspect stderr. Existing installer preservation rules apply.')
        result['installation_completed'] = True
        result['stage'] = 'release_validation'
        # Installer takes this lock itself: acquire only after it has exited.
        # All cooperating installers/rollback/uninstall share the same lock.
        with locked(prefix):
            selected = (prefix / 'current').resolve()
            result['selected_release'] = selected.name
            if selected != prefix / 'releases' / expected_release or release_identity(source) != expected_release:
                raise BootstrapError('Selected release or source changed; refusing readiness/configuration for an unexpected release.')
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
            'installation': 'Installation completion is unconfirmed; inspect installer stderr and selected release before retrying.',
            'release_validation': 'Installer completed, but selected release consistency could not be established; inspect selection before retrying with fresh output.',
            'readiness': 'Installation completed; selected release remains installed. Resolve session readiness, then retry with a fresh output directory.',
            'configuration': 'Installation completed; selected release remains installed. Resolve configuration output failure, then retry with a fresh output directory.',
        }[result['stage']]
        if isinstance(exc, InterruptedProcess):
            result.update(installation_outcome='unknown' if result['stage'] == 'installation' else 'not_attempted',
                          cleanup_verified=exc.cleanup_verified, automatic_retry_allowed=False)
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
