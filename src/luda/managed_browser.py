"""Explicit installer-owned browser selection. No downloads or ambient configuration."""
import hashlib
import json
import os
from pathlib import Path
import platform
import pwd
import re
import selectors
import signal
import stat
import subprocess
import time

CONFIG_NAME = 'luda-browser.json'


def read_config(path):
    path = Path(path)
    if path.is_symlink() or not path.is_file():
        raise ValueError('Browser configuration must be a regular file.')
    info = path.stat()
    if info.st_uid not in (0, os.getuid()) or info.st_mode & 0o022 or info.st_size > 8192:
        raise ValueError('Browser configuration ownership, permissions or size is invalid.')
    try:
        with path.open('rb') as stream:raw=stream.read(8193)
        if len(raw)>8192:raise ValueError('Browser configuration exceeded its size limit.')
        value = json.loads(raw)
    except (ValueError, UnicodeError):
        raise ValueError('Browser configuration must be valid JSON.') from None
    return normalize(value)


def normalize(value):
    if not isinstance(value, dict) or set(value) != {'schema_version','executable','sha256','version','architecture'} or type(value['schema_version']) is not int or value['schema_version'] != 1:
        raise ValueError('Unsupported browser configuration schema.')
    if any(not isinstance(value[k], str) for k in ('executable','sha256','version','architecture')):
        raise ValueError('Browser configuration values must be strings.')
    path = Path(value['executable'])
    if not path.is_absolute() or path.resolve() != path or '..' in path.parts or any(ord(c)<32 for c in str(path)):
        raise ValueError('Browser executable must be an absolute canonical path.')
    if not re.fullmatch('[0-9a-f]{64}', value['sha256']) or not re.fullmatch(r'[0-9]+(?:\.[0-9]+){3}', value['version']):
        raise ValueError('Browser hash or version is invalid.')
    if value['architecture'] not in ('x86_64','aarch64'):
        raise ValueError('Unsupported browser architecture.')
    return {k:value[k] for k in sorted(value)}


def bounded_version(executable, user=None):
    # Even explicit trusted provisioning never starts a browser with root UID.
    kwargs = {}
    if os.getuid() == 0:
        if user is None:raise ValueError('Root provisioning requires an explicit desktop account.')
        try:account = pwd.getpwnam(user)
        except KeyError:raise ValueError('Selected desktop account does not exist.') from None
        if account.pw_uid == 0:raise ValueError('Browser version probe requires an ordinary account.')
        kwargs.update(user=account.pw_uid, group=account.pw_gid, extra_groups=os.getgrouplist(account.pw_name, account.pw_gid))
    process = subprocess.Popen([executable, '--version'], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL, cwd='/', env={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','HOME':'/'}, start_new_session=True, **kwargs)
    data = bytearray(); deadline = time.monotonic()+3
    try:
        with selectors.DefaultSelector() as selector:
            os.set_blocking(process.stdout.fileno(), False)
            selector.register(process.stdout, selectors.EVENT_READ)
            while selector.get_map():
                remaining = deadline-time.monotonic()
                if remaining <= 0:raise ValueError('Browser version probe timed out.')
                for key, _ in selector.select(min(.05,remaining)):
                    chunk=os.read(key.fd,4097-len(data))
                    if not chunk:selector.unregister(key.fileobj)
                    else:data.extend(chunk)
                    if len(data)>4096:raise ValueError('Browser version response exceeded its limit.')
            process.wait(timeout=max(.001,deadline-time.monotonic()))
        if process.returncode:raise ValueError('Browser version probe failed.')
        text=data.decode('utf-8',errors='strict').strip()
        match=re.fullmatch(r'(?:Chromium|Google Chrome(?: for Testing)?|Chrome for Testing) ([0-9]+(?:\.[0-9]+){3})(?: [^\r\n]*)?',text)
        if not match:raise ValueError('Unrecognized browser version response.')
        return match.group(1)
    except (OSError, UnicodeError, subprocess.TimeoutExpired):
        raise ValueError('Browser version probe failed.') from None
    finally:
        try:os.killpg(process.pid,signal.SIGKILL)
        except ProcessLookupError:pass
        process.wait(timeout=3);process.stdout.close()


def verify(value, user=None):
    value=normalize(value);path=Path(value['executable'])
    try:
        with path.open('rb') as stream:
            info=os.fstat(stream.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_mode & 0o022 or not os.access(path,os.X_OK):
                raise ValueError('Browser executable permissions are invalid.')
            header=stream.read(20);stream.seek(0)
            digest=hashlib.file_digest(stream,'sha256').hexdigest()
        machine=int.from_bytes(header[18:20],'little')
        if header[:6] != b'\x7fELF\x02\x01' or machine != {'x86_64':62,'aarch64':183}[value['architecture']] or platform.machine()!=value['architecture']:
            raise ValueError('Browser architecture does not match this Linux host.')
        if digest != value['sha256']:raise ValueError('Browser executable hash changed.')
        observed=bounded_version(str(path), user)
        if observed!=value['version']:raise ValueError('Browser version does not match the selected version.')
        return value
    except OSError:
        raise ValueError('Selected browser executable is unavailable.') from None


def selected(venv, user=None):
    path=Path(venv)/CONFIG_NAME
    return verify(read_config(path), user) if path.exists() or path.is_symlink() else None
