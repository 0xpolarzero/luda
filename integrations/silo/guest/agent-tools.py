#!/usr/bin/env python3
"""Optional Silo guest onboarding. No viewer/SSH credentials or host registration."""
import argparse
import contextlib
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import urllib.parse
import uuid

STATE = Path('/var/lib/silo-agent-tools')
MANIFEST = Path('/usr/local/lib/silo-agent-tools/release.json')
PREFIX = Path('/opt/luda')
USER = 'silo-desktop'
MAX_ARCHIVE = 32 * 1024 * 1024
MAX_EXPANDED = 128 * 1024 * 1024
STATES = {'unconfigured', 'pending', 'ready', 'attention', 'unconfirmed', 'update_available'}
REASONS = {'desktop_status_unavailable', 'source_preparation_failed', 'bootstrap_failed',
           'bootstrap_unconfirmed', 'metadata_unavailable', 'operation_busy'}


class OnboardingError(Exception):
    pass


def atomic(path, value):
    temporary = path.with_name('.' + path.name + '.' + uuid.uuid4().hex)
    try:
        with temporary.open('x') as stream:
            os.chmod(temporary, 0o600)
            json.dump(value, stream)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def read_json(path):
    with path.open('rb') as stream:
        data = stream.read(65537)
    if len(data) > 65536:
        raise OnboardingError('metadata_limit')
    value = json.loads(data)
    if not isinstance(value, dict):
        raise OnboardingError('metadata_shape')
    return value


def manifest(path):
    value = read_json(path)
    if value.get('schema_version') != 1 or type(value.get('enabled')) is not bool:
        raise OnboardingError('manifest_invalid')
    if not value['enabled']:
        if set(value) != {'schema_version', 'enabled'}:
            raise OnboardingError('manifest_invalid')
        return value
    if set(value) != {'schema_version', 'enabled', 'source_url', 'source_sha256', 'source_commit'}:
        raise OnboardingError('manifest_invalid')
    for key, size in (('source_sha256', 64), ('source_commit', 40)):
        if not isinstance(value[key], str) or not re.fullmatch('[0-9a-f]{%d}' % size, value[key]):
            raise OnboardingError('manifest_invalid')
    valid_url(value['source_url'])
    return value


def valid_url(url):
    if not isinstance(url, str) or len(url) > 2048 or any(ord(c) <= 32 for c in url):
        raise OnboardingError('source_url_invalid')
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise OnboardingError('source_url_invalid')


class HttpsRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        valid_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


@contextlib.contextmanager
def download_deadline(seconds):
    # This Linux guest CLI runs on the main thread. A wall-clock alarm also
    # interrupts a peer trickling headers/body below the socket idle timeout.
    if signal.getitimer(signal.ITIMER_REAL)[0]:
        raise OnboardingError('download_timer_in_use')
    previous = signal.getsignal(signal.SIGALRM)
    def expired(signum, frame):
        raise OnboardingError('download_timeout')
    signal.signal(signal.SIGALRM, expired)
    signal.setitimer(signal.ITIMER_REAL, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_REAL, 0)
        signal.signal(signal.SIGALRM, previous)


def download(release, destination, timeout=120):
    with download_deadline(timeout):
        _download(release, destination)


def _download(release, destination):
    digest = hashlib.sha256()
    size = 0
    opener = urllib.request.build_opener(HttpsRedirect())
    with opener.open(release['source_url'], timeout=10) as response, destination.open('xb') as output:
        valid_url(response.geturl())
        while True:
            chunk = response.read1(65536)
            if not chunk:
                break
            size += len(chunk)
            if size > MAX_ARCHIVE:
                raise OnboardingError('archive_limit')
            digest.update(chunk)
            output.write(chunk)
    if digest.hexdigest() != release['source_sha256']:
        raise OnboardingError('source_checksum_mismatch')


def extract(archive, destination, commit):
    """Accept only ordinary files/directories inside the declared archive root."""
    root_name = 'luda-' + commit
    seen = set()
    size = 0
    destination.mkdir(mode=0o700)
    with tarfile.open(archive, 'r:gz') as source:
        for member in source:
            path = PurePosixPath(member.name)
            if (len(seen) >= 10000 or member.name in seen or path.is_absolute()
                    or '..' in path.parts or not path.parts or path.parts[0] != root_name
                    or member.name.rstrip('/') != str(path) or not (member.isdir() or member.isfile())):
                raise OnboardingError('archive_layout_invalid')
            seen.add(member.name)
            size += member.size
            if member.size < 0 or size > MAX_EXPANDED:
                raise OnboardingError('expanded_limit')
            target = destination.joinpath(*path.parts)
            if member.isdir():
                target.mkdir(mode=0o755, parents=True, exist_ok=True)
            else:
                target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
                with source.extractfile(member) as incoming, target.open('xb') as output:
                    shutil.copyfileobj(incoming, output, length=65536)
                target.chmod(0o755 if member.mode & 0o111 else 0o644)
    root = destination / root_name
    for name in ('pyproject.toml', 'MANIFEST.in', 'requirements.lock', 'build-requirements.lock',
                 'scripts/bootstrap_guest.py', 'scripts/manage_install.py', 'scripts/install.sh',
                 'src/luda/server.py', 'skills/luda/SKILL.md'):
        if not (root / name).is_file():
            raise OnboardingError('source_incomplete')
    # mkdir modes are masked by umask, including implicit file-created parents.
    # Keep the enclosing destination private, but copied release skills readable.
    for directory in (root, *(p for p in root.rglob('*') if p.is_dir())):
        directory.chmod(0o755)
    return root


def desktop_running():
    # Only public status; never connection, boot, start, restart or credentials.
    with tempfile.TemporaryFile() as output:
        result = subprocess.run(['/usr/local/bin/silo-desktop', 'status'], stdout=output,
                                stderr=subprocess.DEVNULL, timeout=20, check=False)
        output.seek(0)
        data = output.read(65537)
    if result.returncode or len(data) > 65536:
        raise OnboardingError('desktop_status_invalid')
    value = json.loads(data)
    if not isinstance(value, dict) or value.get('version') != '1' or value.get('installed') is not True or value.get('user') != USER:
        raise OnboardingError('desktop_status_invalid')
    if value.get('state') not in ('running', 'stopped', 'starting', 'failed'):
        raise OnboardingError('desktop_status_invalid')
    return value['state'] == 'running'


def bootstrap(source, output):
    # This is trusted verified source code. Reuse its locks, installer and timeout
    # handling in this process; an outer kill leaves our durable attempt uncertain.
    sys.path.insert(0, str(source / 'scripts'))
    spec = importlib.util.spec_from_file_location('silo_luda_bootstrap', source / 'scripts/bootstrap_guest.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with open(os.devnull, 'w') as sink, contextlib.redirect_stderr(sink), contextlib.redirect_stdout(sink):
        return module.bootstrap(source, PREFIX, output, USER)


def project(value):
    """Strict metadata only: no arbitrary diagnostic text, URL, paths or logs."""
    result = {'schema_version': 1, 'state': value.get('state') if isinstance(value.get('state'), str) and value['state'] in STATES else 'unconfirmed',
              'installation_completed': value.get('installation_completed') if type(value.get('installation_completed')) is bool else None,
              'configuration_generated': value.get('configuration_generated') is True,
              'last_ready': value.get('last_ready') if type(value.get('last_ready')) is bool else None,
              'automatic_retry_allowed': False}
    if result['state'] == 'ready' and any(result[key] is not True for key in
            ('installation_completed', 'configuration_generated', 'last_ready')):
        result['state'] = 'unconfirmed'
    if isinstance(value.get('reason'), str) and value['reason'] in REASONS:
        result['reason'] = value['reason']
    checked = value.get('checked_at')
    if type(checked) is int and 0 <= checked <= 9999999999:
        result['checked_at'] = checked
    for key, pattern in (('source_commit', '[0-9a-f]{40}'), ('source_sha256', '[0-9a-f]{64}'),
                         ('selected_release', '[A-Za-z0-9_.+-]+-[0-9a-f]{16}')):
        if isinstance(value.get(key), str) and re.fullmatch(pattern, value[key]) and len(value[key]) <= 160:
            result[key] = value[key]
    return result


def status(release, state):
    previous = read_json(state / 'status.json') if (state / 'status.json').exists() else {}
    value = project(previous)
    if not release['enabled']:
        value['state'] = 'unconfigured'
    elif not previous:
        value['state'] = 'pending'
    elif value['state'] == 'ready' and (value.get('source_sha256'), value.get('source_commit')) != (release['source_sha256'], release['source_commit']):
        value['state'] = 'update_available'
    return value


def ensure(release, state, *, running=desktop_running, fetch=download, install=bootstrap, reviewed=False):
    """Caller owns state lock. Existing ambiguous/failed attempts never auto-retry."""
    previous = read_json(state / 'status.json') if (state / 'status.json').exists() else {}
    if not release['enabled']:
        return status(release, state)
    if previous and previous.get('state') not in ('pending', 'unconfigured') and not reviewed:
        return status(release, state)
    identity = {key: release[key] for key in ('source_commit', 'source_sha256')}
    try:
        ready = running()
    except Exception:
        value = project({**identity, 'state': 'attention', 'installation_completed': False,
                         'reason': 'desktop_status_unavailable'})
        atomic(state / 'status.json', value)
        return value
    if not ready:
        value = project({**previous, **identity, 'state': 'pending'})
        atomic(state / 'status.json', value)
        return value
    attempt = state / ('attempt-' + uuid.uuid4().hex)
    attempt.mkdir(mode=0o700)
    value = {**identity, 'state': 'unconfirmed', 'installation_completed': False}
    atomic(state / 'status.json', project(value))
    try:
        fetch(release, attempt / 'source.tar.gz')
        source = extract(attempt / 'source.tar.gz', attempt / 'source', release['source_commit'])
        # Persist BEFORE executing any trusted source; no unknown result can mean
        # absence of installation. Never automatically retry this attempt.
        value['installation_completed'] = None
        atomic(state / 'status.json', project(value))
        result = install(source, attempt / 'bundle')
        if not isinstance(result, dict):
            raise OnboardingError('bootstrap_result_invalid')
        completed = result.get('installation_completed')
        value.update(installation_completed=completed if type(completed) is bool else None,
                     configuration_generated=result.get('configuration_generated') is True,
                     last_ready=result.get('tools', {}).get('ready') if isinstance(result.get('tools'), dict) else None,
                     selected_release=result.get('selected_release'))
        if type(value['last_ready']) is bool:
            value['checked_at'] = int(time.time())
        value['state'] = 'ready' if result.get('ok') is True and value['installation_completed'] is True and value['configuration_generated'] and value['last_ready'] is True else 'attention' if value['installation_completed'] is not None else 'unconfirmed'
        if value['state'] != 'ready':
            value['reason'] = 'bootstrap_unconfirmed' if value['installation_completed'] is None else 'bootstrap_failed'
    except Exception:
        value['state'] = 'attention' if value['installation_completed'] is False else 'unconfirmed'
        value['reason'] = 'source_preparation_failed' if value['installation_completed'] is False else 'bootstrap_unconfirmed'
    value = project(value)
    atomic(state / 'status.json', value)
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('status', 'ensure', 'retry-after-review'))
    args = parser.parse_args()
    value = {'state': 'attention', 'reason': 'metadata_unavailable'}
    try:
        if os.geteuid() != 0:
            raise OnboardingError('root_required')
        if STATE.is_symlink() or STATE.exists() and (STATE.stat().st_uid != 0 or STATE.stat().st_mode & 0o022):
            raise OnboardingError('state_permissions')
        STATE.mkdir(mode=0o700, parents=True, exist_ok=True)
        release = manifest(MANIFEST)
        if args.action == 'status':
            value = status(release, STATE)
        else:
            fd = os.open(STATE / 'operation.lock', os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                value = ensure(release, STATE, reviewed=args.action == 'retry-after-review')
            finally:
                os.close(fd)
    except BlockingIOError:
        value = {'state': 'unconfirmed', 'reason': 'operation_busy'}
    except Exception:
        pass
    # Onboarding failure is independent of desktop setup/viewer availability.
    print(json.dumps(project(value)))


if __name__ == '__main__':
    main()
