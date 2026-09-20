#!/usr/bin/env python3
"""Opt-in pinned official ARM64 Firefox for qualification, never runtime install."""
import argparse
import hashlib
import json
from pathlib import Path
import tarfile
import urllib.request

VERSION = '156.0'
BASE = f'https://archive.mozilla.org/pub/firefox/releases/{VERSION}/'
ARCHIVE = f'linux-aarch64/en-US/firefox-{VERSION}.tar.xz'
SHA256 = '7dd9425eafa0decf61c0f6bc56dc71cba84595495dc01395d3eea38a18aaf710'


def main(directory):
    directory = Path(directory).resolve()
    # A new dedicated directory prevents overwriting another installation.
    directory.mkdir(parents=True, exist_ok=False)
    sums = urllib.request.urlopen(BASE + 'SHA256SUMS', timeout=60).read(2_000_000)
    candidates = [line.split()[0] for line in sums.decode().splitlines() if line.split()[-1] == ARCHIVE]
    if candidates != [SHA256]:
        raise RuntimeError('Upstream checksum no longer matches the pinned release')
    (directory / 'SHA256SUMS').write_bytes(sums)
    archive = directory / Path(ARCHIVE).name
    with urllib.request.urlopen(BASE + ARCHIVE, timeout=60) as response, archive.open('xb') as out:
        digest = hashlib.sha256()
        while chunk := response.read(1024 * 1024):
            digest.update(chunk);out.write(chunk)
    if digest.hexdigest() != SHA256:
        raise RuntimeError('Downloaded archive checksum mismatch; extraction refused')
    with tarfile.open(archive) as package:
        package.extractall(directory, filter='data')
    executable = directory / 'firefox/firefox'
    manifest = {'version':VERSION,'architecture':'linux-aarch64','archive_url':BASE+ARCHIVE,
                'upstream_checksums_url':BASE+'SHA256SUMS','archive_sha256':SHA256,
                'executable_sha256':hashlib.sha256(executable.read_bytes()).hexdigest()}
    (directory / 'provision.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(executable)

if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',required=True,help='New external test-only directory')
    main(parser.parse_args().directory)
