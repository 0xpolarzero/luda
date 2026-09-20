#!/usr/bin/env python3
"""Prepare exact committed source and a Silo manifest; never publish or install."""
import argparse
import gzip
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import re
import subprocess
import tarfile
import tempfile
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {'pyproject.toml', 'MANIFEST.in', 'requirements.lock', 'build-requirements.lock',
            'scripts/bootstrap_guest.py', 'scripts/manage_install.py', 'scripts/install.sh',
            'src/luda/server.py', 'skills/luda/SKILL.md'}


def git(repo, *args):
    return subprocess.check_output(['git', '-C', str(repo), *args], stderr=subprocess.PIPE, timeout=30)


def prepare(repo, commit, source_url, output):
    if not isinstance(commit, str) or not re.fullmatch('[0-9a-f]{40}', commit):
        raise ValueError('Use an exact lowercase 40-character commit identifier.')
    if not isinstance(source_url, str) or len(source_url) > 2048:
        raise ValueError('Source URL must be a string of at most 2048 characters.')
    url = urlsplit(source_url)
    if (url.scheme != 'https' or not url.hostname or url.username is not None or url.password is not None
            or url.query or url.fragment or any(ord(c) <= 32 or ord(c) == 127 for c in source_url)):
        raise ValueError('Source URL must be HTTPS without credentials, whitespace, query or fragment.')
    name = 'luda-' + commit + '.tar.gz'
    if PurePosixPath(url.path).name != name:
        raise ValueError('Source URL must end with the exact generated archive filename.')
    if git(repo, 'cat-file', '-t', commit).strip() != b'commit':
        raise ValueError('Identifier must name a commit object.')
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError('Choose a fresh output directory.')
    expected = {}
    for row in git(repo, 'ls-tree', '-rz', '--full-tree', commit).split(b'\0'):
        if not row:
            continue
        header, raw_path = row.split(b'\t', 1)
        mode, kind, digest = header.split()
        path = raw_path.decode('utf-8')
        if mode not in (b'100644', b'100755') or kind != b'blob':
            raise ValueError('Source must contain only ordinary files; no symlinks or submodules.')
        if any(ord(c) < 32 for c in path) or '..' in PurePosixPath(path).parts:
            raise ValueError('Source path is outside the archive contract.')
        expected[path] = (mode == b'100755', digest.decode('ascii'))
    if not REQUIRED <= expected.keys() or len(expected) >= 10000:
        raise ValueError('Committed source is incomplete or exceeds the guest file limit.')
    prefix = 'luda-' + commit
    raw = git(repo, 'archive', '--format=tar', '--prefix=' + prefix + '/', commit)
    seen = set()
    expanded = 0
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:') as archive:
        entries = 0
        for member in archive:
            entries += 1
            path = PurePosixPath(member.name)
            if (entries > 10000 or path.is_absolute() or '..' in path.parts
                    or not path.parts or path.parts[0] != prefix
                    or member.name.rstrip('/') != str(path)):
                raise ValueError('Generated archive has an invalid layout.')
            if member.isdir():
                continue
            relative = str(PurePosixPath(*path.parts[1:]))
            if not member.isfile() or relative in seen or relative not in expected:
                raise ValueError('Generated archive differs from the committed file tree.')
            data = archive.extractfile(member).read()
            expanded += len(data)
            executable, object_hash = expected[relative]
            actual = hashlib.sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()
            if actual != object_hash or bool(member.mode & 0o111) != executable:
                raise ValueError('Archive attributes changed committed file content or mode.')
            seen.add(relative)
    if seen != expected.keys() or expanded > 128 * 1024 * 1024:
        raise ValueError('Archive omits committed files or exceeds the expanded guest limit.')
    compressed = gzip.compress(raw, mtime=0)
    if len(compressed) > 32 * 1024 * 1024:
        raise ValueError('Archive exceeds the guest download limit.')
    digest = hashlib.sha256(compressed).hexdigest()
    manifest = {'schema_version': 1, 'enabled': True, 'source_url': source_url,
                'source_sha256': digest, 'source_commit': commit}
    provenance = {'schema_version': 1, 'commit': commit,
                  'tree': git(repo, 'rev-parse', commit + '^{tree}').decode().strip(),
                  'archive': name, 'sha256': digest, 'bytes': len(compressed),
                  'files': len(seen), 'expanded_file_bytes': expanded,
                  'git_version': git(repo, '--version').decode().strip(),
                  'scope': 'Exact local Git objects and archive bytes; not a signature, published URL check, or release qualification.'}
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.luda-release-', dir=output.parent) as temporary:
        stage = Path(temporary) / 'release'
        stage.mkdir()
        (stage / name).write_bytes(compressed)
        (stage / 'SHA256SUMS').write_text(digest + '  ' + name + '\n')
        for filename, value in [('agent-tools-release.json', manifest), ('provenance.json', provenance)]:
            (stage / filename).write_text(json.dumps(value, indent=2) + '\n')
        stage.rename(output)
    return provenance


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--commit', required=True)
    parser.add_argument('--source-url', required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(ROOT, args.commit, args.source_url, args.output), indent=2))


if __name__ == '__main__':
    main()
