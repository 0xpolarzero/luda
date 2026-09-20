#!/usr/bin/env python3
"""Build a self-contained Codex plugin without modifying agent configuration."""
import argparse
import json
from pathlib import Path
import re
import shutil
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def mcp_config(prefix, user='silo-desktop', remote=False):
    prefix = str(prefix)
    if not Path(prefix).is_absolute() or prefix == '/' or any(ord(c) < 32 for c in prefix):
        raise ValueError('Guest prefix must be an absolute non-root path without control characters.')
    if '..' in Path(prefix).parts or '~' in prefix:
        raise ValueError('Guest prefix must not contain traversal or shell expansion.')
    if not re.fullmatch(r'[a-z_][a-z0-9_-]*[$]?', user):
        raise ValueError('Desktop user must be a Linux account name.')
    release = Path(prefix) / 'current/.venv/bin'
    server = {'command': str(release / 'luda-session'),
              'args': ['--user', user, '--', str(release / 'luda')]}
    if remote:
        server['experimental_environment'] = 'remote'
    return {'mcpServers': {'luda': server}}


def build(output, prefix, user='silo-desktop', remote=False):
    config = mcp_config(prefix, user, remote)
    output = Path(output).absolute()
    if output.name != 'luda':
        raise ValueError('Plugin output folder must be named luda.')
    if output.exists() or output.is_symlink():
        raise FileExistsError('Output exists; choose a fresh bundle directory.')
    if (ROOT / 'skills/luda').is_symlink() or any(path.is_symlink() for path in (ROOT / 'skills/luda').rglob('*')):
        raise ValueError('Bundled skills must not contain symbolic links.')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.luda-plugin-', dir=output.parent) as directory:
        stage = Path(directory) / 'luda'
        (stage / '.codex-plugin').mkdir(parents=True)
        shutil.copy2(ROOT / '.codex-plugin/plugin.json', stage / '.codex-plugin/plugin.json')
        shutil.copytree(ROOT / 'skills/luda', stage / 'skills/luda')
        shutil.copy2(ROOT / 'LICENSE', stage / 'LICENSE')
        (stage / '.mcp.json').write_text(json.dumps(config, indent=2) + '\n')
        stage.rename(output)
    return output


def build_marketplace(output, prefix, user='silo-desktop', remote=False):
    output = Path(output).absolute()
    if output.exists() or output.is_symlink():
        raise FileExistsError('Marketplace output exists; choose a fresh directory.')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.luda-marketplace-', dir=output.parent) as directory:
        stage = Path(directory) / 'marketplace'
        build(stage / 'plugins/luda', prefix, user, remote)
        catalog = stage / '.agents/plugins'
        catalog.mkdir(parents=True)
        manifest = {'name': 'luda-local', 'interface': {'displayName': 'Luda'},
                    'plugins': [{'name': 'luda', 'source': {'source': 'local', 'path': './plugins/luda'},
                                 'policy': {'installation': 'AVAILABLE', 'authentication': 'ON_INSTALL'},
                                 'category': 'Productivity'}]}
        (catalog / 'marketplace.json').write_text(json.dumps(manifest, indent=2) + '\n')
        stage.rename(output)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    destination = parser.add_mutually_exclusive_group(required=True)
    destination.add_argument('--output', type=Path, help='Fresh plugin directory named luda')
    destination.add_argument('--marketplace-root', type=Path, help='Fresh standalone local marketplace directory')
    parser.add_argument('--prefix', required=True, help='Installed release prefix on the Linux guest')
    parser.add_argument('--user', default='silo-desktop')
    parser.add_argument('--remote', action='store_true', help='Request an available Codex remote executor; host integration must be verified')
    args = parser.parse_args()
    try:
        builder = build_marketplace if args.marketplace_root else build
        print(builder(args.marketplace_root or args.output, args.prefix, args.user, args.remote))
    except (ValueError, OSError) as exc:
        parser.exit(1, f'{exc}\n')
