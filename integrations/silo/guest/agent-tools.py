#!/usr/bin/env python3
"""Optional Silo guest onboarding. No viewer/SSH credentials or host registration."""
import argparse
import contextlib
import fcntl
import hashlib
import gzip
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
import zlib

STATE = Path('/var/lib/silo-agent-tools')
MANIFEST = Path('/usr/local/lib/silo-agent-tools/release.json')
PREFIX = Path('/opt/luda')
USER = 'silo-desktop'
MAX_ARCHIVE = 32 * 1024 * 1024
MAX_EXPANDED = 128 * 1024 * 1024
MAX_TAR_STREAM = 128 * 1024 * 1024
STATES = {'unconfigured', 'pending', 'ready', 'attention', 'unconfirmed', 'update_available'}
REASONS = {'desktop_status_unavailable', 'source_preparation_failed', 'bootstrap_failed',
           'bootstrap_unconfirmed', 'metadata_unavailable', 'operation_busy', 'browser_candidate_unavailable',
           'browser_candidate_invalid', 'browser_selection_invalid', 'browser_source_unsupported'}


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
    if set(value) not in ({'schema_version', 'enabled', 'source_url', 'source_sha256', 'source_commit'}, {'schema_version', 'enabled', 'source_url', 'source_sha256', 'source_commit', 'browser'}):
        raise OnboardingError('manifest_invalid')
    for key, size in (('source_sha256', 64), ('source_commit', 40)):
        if not isinstance(value[key], str) or not re.fullmatch('[0-9a-f]{%d}' % size, value[key]):
            raise OnboardingError('manifest_invalid')
    valid_url(value['source_url'])
    if 'browser' in value:value['browser']=browser_candidate(value['browser'])
    return value


def browser_candidate(value):
    # Structural trust declaration only. The selected source installer verifies
    # actual ELF architecture, executable digest/version and account access.
    if not isinstance(value,dict) or set(value)!={'schema_version','executable','sha256','version','architecture'} or type(value['schema_version']) is not int or value['schema_version']!=1:
        raise OnboardingError('browser_candidate_invalid')
    path=value.get('executable')
    if not isinstance(path,str) or len(path)>4096 or not path.startswith('/') or '..' in PurePosixPath(path).parts or any(ord(c)<32 for c in path):raise OnboardingError('browser_candidate_invalid')
    if not isinstance(value['sha256'],str) or not re.fullmatch('[0-9a-f]{64}',value['sha256']):raise OnboardingError('browser_candidate_invalid')
    if not isinstance(value['version'],str) or not re.fullmatch(r'[0-9]+(?:\.[0-9]+){3}',value['version']) or value['architecture'] not in ('aarch64','x86_64'):raise OnboardingError('browser_candidate_invalid')
    return {key:value[key] for key in sorted(value)}


def browser_request(state):
    path=state/'browser-selection.json'
    if not path.exists():return False
    value=read_json(path)
    if set(value)!={'enabled'} or type(value['enabled']) is not bool:raise OnboardingError('browser_selection_invalid')
    return value['enabled']


def browser_identity(release,state):
    enabled=release.get('enabled') is True and browser_request(state)
    if enabled and 'browser' not in release:raise OnboardingError('browser_candidate_unavailable')
    value=browser_candidate(release['browser']) if enabled else None
    return value,hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def set_browser(release,state,enabled,**kwargs):
    # Explicit actions share the existing operation lock. Unconfirmed attempts
    # cannot be overridden with a second provisioning action.
    if not release['enabled'] or enabled and 'browser' not in release:raise OnboardingError('browser_candidate_unavailable')
    previous=read_json(state/'status.json') if (state/'status.json').exists() else {}
    if previous.get('state')=='unconfirmed':raise OnboardingError('bootstrap_unconfirmed')
    if enabled:browser_candidate(release['browser'])
    atomic(state/'browser-selection.json',{'enabled':enabled})
    return ensure(release,state,reviewed=True,**kwargs)


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


class BoundedTarFile:
    """Clamp parser reads to validated bytes, regardless of declared member size."""
    def __init__(self, file, size):
        self.file, self.size = file, size

    def tell(self):
        return self.file.tell()

    def read(self, size=-1):
        remaining = self.size - self.tell()
        return self.file.read(remaining if size < 0 else min(size, remaining))

    def seek(self, offset, whence=0):
        position = offset + (self.tell() if whence == 1 else self.size if whence == 2 else 0)
        if whence not in (0, 1, 2) or not 0 <= position <= self.size:
            raise OnboardingError('archive_invalid')
        return self.file.seek(position)


@contextlib.contextmanager
def bounded_tar_stream(archive, temporary_directory):
    """Validate the entire expanded stream before tarfile can parse metadata."""
    try:
        with tempfile.TemporaryFile(dir=temporary_directory) as expanded:
            with gzip.open(archive, 'rb') as compressed:
                total = 0
                while True:
                    chunk = compressed.read(min(65536, MAX_TAR_STREAM - total + 1))
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > MAX_TAR_STREAM:
                        raise OnboardingError('tar_stream_limit')
                    expanded.write(chunk)
            expanded.seek(0)
            yield BoundedTarFile(expanded, total)
    except (OSError, EOFError, OverflowError, ValueError, RecursionError, zlib.error, tarfile.TarError):
        raise OnboardingError('archive_invalid') from None


def extract(archive, destination, commit):
    """Accept only ordinary files/directories inside the declared archive root."""
    root_name = 'luda-' + commit
    seen = set()
    size = 0
    with bounded_tar_stream(archive, destination.parent) as expanded, tarfile.open(fileobj=expanded, mode='r:') as source:
        destination.mkdir(mode=0o700)
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


def bootstrap(source, output, browser_config=None):
    # This is trusted verified source code. Reuse its locks, installer and timeout
    # handling in this process; an outer kill leaves our durable attempt uncertain.
    sys.path.insert(0, str(source / 'scripts'))
    spec = importlib.util.spec_from_file_location('silo_luda_bootstrap', source / 'scripts/bootstrap_guest.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    with open(os.devnull, 'w') as sink, contextlib.redirect_stderr(sink), contextlib.redirect_stdout(sink):
        return module.bootstrap(source, PREFIX, output, USER, **({'browser_config':browser_config} if browser_config is not None else {}))


def project(value):
    """Strict metadata only: no arbitrary diagnostic text, URL, paths or logs."""
    result = {'schema_version': 1, 'state': value.get('state') if isinstance(value.get('state'), str) and value['state'] in STATES else 'unconfirmed',
              'installation_completed': value.get('installation_completed') if type(value.get('installation_completed')) is bool else None,
              'configuration_generated': value.get('configuration_generated') is True,
              'last_ready': value.get('last_ready') if type(value.get('last_ready')) is bool else None,
              'automatic_retry_allowed': False,
              'browser_available': value.get('browser_available') is True,
              'browser_requested': value.get('browser_requested') is True,
              'browser_configured': value.get('browser_configured') if type(value.get('browser_configured')) is bool else None}
    if result['state'] == 'ready' and any(result[key] is not True for key in
            ('installation_completed', 'configuration_generated', 'last_ready')):
        result['state'] = 'unconfirmed'
    if isinstance(value.get('reason'), str) and value['reason'] in REASONS:
        result['reason'] = value['reason']
    checked = value.get('checked_at')
    if type(checked) is int and 0 <= checked <= 9999999999:
        result['checked_at'] = checked
    for key, pattern in (('source_commit', '[0-9a-f]{40}'), ('source_sha256', '[0-9a-f]{64}'),
                         ('selected_release', '[A-Za-z0-9_.+-]+-[0-9a-f]{16}'), ('browser_config_sha256','[0-9a-f]{64}')):
        if isinstance(value.get(key), str) and re.fullmatch(pattern, value[key]) and len(value[key]) <= 160:
            result[key] = value[key]
    return result


def status(release, state):
    previous = read_json(state / 'status.json') if (state / 'status.json').exists() else {}
    value = project(previous)
    try:requested, digest = browser_identity(release,state)
    except OnboardingError:
        value.update(state='attention',reason='browser_candidate_unavailable',browser_available=False,browser_requested=browser_request(state))
        return value
    value.update(browser_available=release['enabled'] and 'browser' in release, browser_requested=requested is not None)
    if not release['enabled']:
        value['state'] = 'unconfigured'
    elif not previous:
        value['state'] = 'pending'
    elif value['state'] == 'ready' and (value.get('source_sha256'), value.get('source_commit')) != (release['source_sha256'], release['source_commit']):
        value['state'] = 'update_available'
    if value['state']=='ready' and value.get('browser_config_sha256',hashlib.sha256(b'null').hexdigest())!=digest:value['state']='update_available'
    return value


def ensure(release, state, *, running=desktop_running, fetch=download, install=bootstrap, reviewed=False):
    """Caller owns state lock. Existing ambiguous/failed attempts never auto-retry."""
    previous = read_json(state / 'status.json') if (state / 'status.json').exists() else {}
    if not release['enabled']:
        return status(release, state)
    if previous and previous.get('state') not in ('pending', 'unconfigured') and not reviewed:
        return status(release, state)
    candidate,digest=browser_identity(release,state)
    identity = {key: release[key] for key in ('source_commit', 'source_sha256')}
    identity.update(browser_available='browser' in release,browser_requested=candidate is not None,browser_config_sha256=digest)
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
    value = {**identity, 'state': 'unconfirmed', 'installation_completed': False, 'browser_configured':previous.get('browser_configured')}
    atomic(state / 'status.json', project(value))
    try:
        fetch(release, attempt / 'source.tar.gz')
        source = extract(attempt / 'source.tar.gz', attempt / 'source', release['source_commit'])
        if candidate is not None and (not (source/'requirements-browser.lock').is_file() or not (source/'src/luda/managed_browser.py').is_file()):raise OnboardingError('browser_source_unsupported')
        # Persist BEFORE executing any trusted source; no unknown result can mean
        # absence of installation. Never automatically retry this attempt.
        value['installation_completed'] = None
        atomic(state / 'status.json', project(value))
        if candidate is not None:
            # Fail before invoking an older bootstrap lacking this explicit API.
            config_path=attempt/'browser.json';atomic(config_path,candidate)
            result = install(source, attempt / 'bundle', browser_config=config_path)
        else:result = install(source, attempt / 'bundle')
        if not isinstance(result, dict):
            raise OnboardingError('bootstrap_result_invalid')
        completed = result.get('installation_completed')
        value.update(installation_completed=completed if type(completed) is bool else None,
                     configuration_generated=result.get('configuration_generated') is True,
                     last_ready=result.get('tools', {}).get('ready') if isinstance(result.get('tools'), dict) else None,
                     selected_release=result.get('selected_release'))
        if type(value['last_ready']) is bool:
            value['checked_at'] = int(time.time())
        completed = result.get('ok') is True and value['installation_completed'] is True and value['configuration_generated'] and value['last_ready'] is True
        value['browser_configured'] = (candidate is not None) if completed else None
        value['state'] = 'ready' if completed else 'attention' if value['installation_completed'] is not None else 'unconfirmed'
        if value['state'] != 'ready':
            value['reason'] = 'bootstrap_unconfirmed' if value['installation_completed'] is None else 'bootstrap_failed'
    except Exception as exc:
        value['state'] = 'attention' if value['installation_completed'] is False else 'unconfirmed'
        value['reason'] = str(exc) if isinstance(exc,OnboardingError) and str(exc) in REASONS else 'source_preparation_failed' if value['installation_completed'] is False else 'bootstrap_unconfirmed'
    value = project(value)
    atomic(state / 'status.json', value)
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('status', 'ensure', 'retry-after-review', 'enable-browser', 'disable-browser'))
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
                value = set_browser(release,STATE,args.action=='enable-browser') if args.action in ('enable-browser','disable-browser') else ensure(release, STATE, reviewed=args.action == 'retry-after-review')
            finally:
                os.close(fd)
    except OnboardingError as exc:
        value = {'state':'attention','reason':str(exc)}
    except BlockingIOError:
        value = {'state': 'unconfirmed', 'reason': 'operation_busy'}
    except Exception:
        pass
    # Onboarding failure is independent of desktop setup/viewer availability.
    print(json.dumps(project(value)))


if __name__ == '__main__':
    main()
