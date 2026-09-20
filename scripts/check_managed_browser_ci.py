#!/usr/bin/env python3
"""Qualify an installed managed release using the explicitly provisioned CI browser."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import pwd
import subprocess
import sys

from qualify import source_fingerprint

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--prefix', type=Path, required=True)
    parser.add_argument('--executable', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if os.getuid() == 0:
        parser.error('Use an ordinary CI account on a private desktop')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    before = source_fingerprint()
    executable = args.executable.resolve(strict=True)
    config = output / 'browser.json'
    config.write_text(json.dumps({'schema_version': 1, 'executable': str(executable),
        'sha256': hashlib.sha256(executable.read_bytes()).hexdigest(),
        'version': '153.0.8010.12', 'architecture': platform.machine()}, indent=2) + '\n')
    config.chmod(0o600)
    # This digest binds the already-provisioned CI file. It is not an independent
    # authenticity check or a promise about adjacent browser distribution files.
    with (output / 'install.log').open('w') as log:
        subprocess.run([sys.executable, str(ROOT / 'scripts/manage_install.py'), 'install',
            '--prefix', str(args.prefix.resolve()), '--browser-config', str(config),
            '--user', pwd.getpwuid(os.getuid()).pw_name], check=True, stdout=log,
            stderr=subprocess.STDOUT, timeout=600)
    release = (args.prefix / 'current').resolve(strict=True)
    installed_python = release / '.venv/bin/python'
    package = Path(subprocess.check_output([str(installed_python), '-c',
        'import pathlib,luda;print(pathlib.Path(luda.__file__).parent)'], text=True).strip())
    hashes = {}
    source_files = sorted((ROOT / 'src/luda').rglob('*.py'))
    assert {p.relative_to(package) for p in package.rglob('*.py')} == {p.relative_to(ROOT / 'src/luda') for p in source_files}
    for source in source_files:
        relative = source.relative_to(ROOT / 'src/luda')
        assert source.read_bytes() == (package / relative).read_bytes(), relative
        hashes[str(relative)] = hashlib.sha256(source.read_bytes()).hexdigest()
    (output / 'runtime-hashes.json').write_text(json.dumps(hashes, indent=2) + '\n')
    subprocess.run([sys.executable, str(ROOT / 'tests/evidence/managed-browser/run.py'),
        '--repo', str(ROOT), '--prefix', str(args.prefix.resolve()),
        '--output', str(output / 'live')], check=True, timeout=120)
    after = source_fingerprint()
    assert before == after, 'Source changed during installed qualification'
    (output / 'source.json').write_text(json.dumps({'before': before, 'after': after,
        'unchanged': True, 'runtime_modules': len(hashes), 'release': release.name,
        'scope': 'CI provisioned executable; installed wheel and ordinary-account launcher; replacement test unexercised'}, indent=2) + '\n')


if __name__ == '__main__':
    main()
