#!/usr/bin/env python3
"""Build separate core/add-on release assets from a clean committed checkout."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def git(*args):
    return subprocess.check_output(['git', '-C', str(ROOT), *args], text=True).strip()


def plugin_zip(source, target, name):
    required = [source / '.codex-plugin/plugin.json', source / '.mcp.json', source / 'skills' / name / 'SKILL.md']
    if not all(p.is_file() for p in required):
        raise ValueError(f'Missing plugin files for {name}')
    plugin_name = json.loads(required[0].read_text()).get('name')
    if not isinstance(plugin_name, str) or not plugin_name or any(c not in 'abcdefghijklmnopqrstuvwxyz0123456789-' for c in plugin_name):
        raise ValueError('Invalid plugin name')
    files = list(dict.fromkeys(required + sorted((source / 'skills' / name).rglob('*'))))
    license_file = source / 'LICENSE'
    if license_file.is_file():
        files.append(license_file)
    with zipfile.ZipFile(target, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            if path.is_symlink():
                raise ValueError('Plugin assets must not be symbolic links')
            if path.is_file():
                archive.write(path, str(Path(plugin_name) / path.relative_to(source)))


def verify_wheel(source, wheel, package, skill):
    expected = {str(p.relative_to(source / 'src')): p.read_bytes()
                for p in (source / 'src' / package).rglob('*.py')}
    if not (source / 'skills' / skill / 'SKILL.md').is_file():
        raise ValueError('Missing packaged skill entrypoint')
    if not expected:
        raise ValueError('No runtime modules found')
    with zipfile.ZipFile(wheel) as archive:
        actual = {name: archive.read(name) for name in archive.namelist()
                  if name.startswith(package + '/') and name.endswith('.py')}
        if actual != expected:
            raise ValueError('Wheel runtime differs from source')
        for path in (source / 'skills' / skill).rglob('*'):
            if not path.is_file():
                continue
            suffix = '/skills/' + skill + '/' + str(path.relative_to(source / 'skills' / skill))
            candidates = [n for n in archive.namelist() if n.endswith(suffix)]
            if len(candidates) != 1 or archive.read(candidates[0]) != path.read_bytes():
                raise ValueError(f'Wheel skill asset missing or changed: {path.name}')
        if package == 'luda' and any('prosemirror' in n or 'luda_editor_bridge/' in n for n in archive.namelist()):
            raise ValueError('Core wheel must not bundle the optional editor add-on')
    return len(expected)


def build(output):
    output = output.absolute()
    if output.exists() or output.is_symlink():
        raise ValueError('Choose a fresh output directory')
    if git('status', '--porcelain', '--untracked-files=normal'):
        raise ValueError('Commit changes first; release assets must match a clean Git revision')
    if not all(importlib.util.find_spec(name) for name in ('setuptools', 'wheel')):
        raise ValueError('Install build-requirements.lock into the build environment first')
    revision = git('rev-parse', 'HEAD')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.luda-release-', dir=output.parent) as temporary:
        base = Path(temporary)
        archive_path = base / 'source.tar'
        with archive_path.open('wb') as stream:
            subprocess.run(['git', '-C', str(ROOT), 'archive', revision], stdout=stream, check=True)
        source = base / 'source'
        source.mkdir()
        with tarfile.open(archive_path) as archive:
            archive.extractall(source, filter='data')
        assets = base / 'assets'
        assets.mkdir()
        checks = {}
        projects = [(source, 'luda', 'luda'),
                    (source / 'addons/editor-bridge', 'luda_editor_bridge', 'luda-editor-bridge')]
        for project, package, skill in projects:
            metadata = tomllib.loads((project / 'pyproject.toml').read_text())['project']
            before = set(assets.glob('*.whl'))
            before_source = set(assets.glob('*.tar.gz'))
            subprocess.run([sys.executable, '-I', '-c',
                'import sys; from setuptools import build_meta; build_meta.build_wheel(sys.argv[1]); build_meta.build_sdist(sys.argv[1])',
                str(assets)], cwd=project, check=True)
            wheels = set(assets.glob('*.whl')) - before
            if len(wheels) != 1:
                raise ValueError('Expected exactly one wheel per distribution')
            wheel = wheels.pop()
            sources = set(assets.glob('*.tar.gz')) - before_source
            if len(sources) != 1:
                raise ValueError('Expected exactly one source archive per distribution')
            if package == 'luda':
                with tarfile.open(sources.pop()) as distribution:
                    if any('/addons/' in n or '/integrations/prosemirror/' in n for n in distribution.getnames()):
                        raise ValueError('Core source archive must not bundle the editor add-on')
            checks[metadata['name']] = {'version': metadata['version'],
                'runtime_modules': verify_wheel(project, wheel, package, skill), 'skill_matches': True}
            plugin_zip(project, assets / f'{skill}-plugin-{metadata["version"]}.zip', skill)
        manifest = {'source_commit': revision, 'packages': checks,
                    'installation': 'Core and editor add-on are separate installations. Plugin archives contain configuration and skills, not the Python runtime.'}
        (assets / 'release.json').write_text(json.dumps(manifest, indent=2) + '\n')
        files = sorted(p for p in assets.iterdir() if p.is_file())
        (assets / 'SHA256SUMS').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest() + '  ' + p.name + '\n' for p in files))
        shutil.move(str(assets), output)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        print(build(args.output))
    except (ValueError, OSError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f'{exc}\n')
