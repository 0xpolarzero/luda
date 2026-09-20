#!/usr/bin/env python3
"""Build a self-contained Codex plugin without modifying agent configuration."""
import argparse
import hashlib
import shlex
import uuid
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


def host_ssh_config(prefix, user, ssh_executable, ssh_config, ssh_alias):
    local = mcp_config(prefix, user)['mcpServers']['luda']
    for value in (ssh_executable, ssh_config):
        if not Path(value).is_absolute() or any(ord(c) < 32 for c in str(value)):
            raise ValueError('SSH executable and configuration must be absolute literal host paths.')
    if not isinstance(ssh_alias, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,127}', ssh_alias):
        raise ValueError('SSH alias must be a literal host alias, not options or a URL.')
    # OpenSSH passes its remote command through a shell even with local argv.
    remote_command = shlex.join([local['command'], *local['args']])
    return {'mcpServers': {'luda': {'command': str(ssh_executable),
        'args': ['-T', '-F', str(ssh_config), '-o', 'BatchMode=yes',
                 '-o', 'StrictHostKeyChecking=yes', '-o', 'ForwardAgent=no',
                 '-o', 'ForwardX11=no', ssh_alias, remote_command]}}}


def build_host_marketplace(output, prefix, vm_id, skill_file, skill_sha256,
                           ssh_config, ssh_alias, ssh_executable='/usr/bin/ssh', user='silo-desktop'):
    """Build a fixed-VM host plugin; caller supplies a trusted expected skill hash."""
    identity = uuid.UUID(vm_id).hex
    name = 'luda-' + identity
    marketplace = 'silo-' + identity
    config = host_ssh_config(prefix, user, ssh_executable, ssh_config, ssh_alias)
    server_name = 'ld-' + identity
    config['mcpServers'] = {server_name: config['mcpServers']['luda']}
    if not isinstance(skill_sha256, str) or not re.fullmatch('[0-9a-f]{64}', skill_sha256):
        raise ValueError('Expected skill SHA-256 must come from the verified guest release.')
    skill_file = Path(skill_file)
    if skill_file.is_symlink() or not skill_file.is_file():
        raise ValueError('Skill artifact must be an ordinary local file.')
    with skill_file.open('rb') as stream:
        skill = stream.read(262145)
    if len(skill) > 262144 or hashlib.sha256(skill).hexdigest() != skill_sha256:
        raise ValueError('Skill artifact size or SHA-256 does not match.')
    skill.decode('utf-8')
    output = Path(output)
    if not output.is_absolute():
        raise ValueError('Choose an explicit persistent absolute host marketplace path.')
    if output.exists() or output.is_symlink():
        raise FileExistsError('Output exists; do not replace a registered marketplace in place.')
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.luda-host-', dir=output.parent) as directory:
        stage = Path(directory)/'marketplace'
        plugin = stage/'plugins'/name
        (plugin/'.codex-plugin').mkdir(parents=True)
        manifest = json.loads((ROOT/'.codex-plugin/plugin.json').read_text())
        manifest.update(name=name, version=manifest['version']+'+ssh.'+hashlib.sha256(
            json.dumps(config,sort_keys=True).encode()+skill).hexdigest()[:16])
        manifest['interface']['displayName'] = 'Luda desktop '+str(uuid.UUID(vm_id))
        manifest['description'] = 'Control desktop of Silo VM '+str(uuid.UUID(vm_id))+'. The bundled skill is generic guidance; select this VM-specific tool server.'
        (plugin/'.codex-plugin/plugin.json').write_text(json.dumps(manifest,indent=2)+'\n')
        (plugin/'skills/luda').mkdir(parents=True)
        (plugin/'skills/luda/SKILL.md').write_bytes(skill)
        shutil.copy2(ROOT/'LICENSE',plugin/'LICENSE')
        (plugin/'.mcp.json').write_text(json.dumps(config,indent=2)+'\n')
        catalog = stage/'.agents/plugins';catalog.mkdir(parents=True)
        (catalog/'marketplace.json').write_text(json.dumps({'name':marketplace,'plugins':[
            {'name':name,'source':{'source':'local','path':'./plugins/'+name},
             'policy':{'installation':'AVAILABLE','authentication':'ON_INSTALL'},'category':'Productivity'}]},indent=2)+'\n')
        metadata = {'format':1,'vm_id':str(uuid.UUID(vm_id)),'plugin':name,'marketplace':marketplace,
                    'server_name':server_name,'ssh_alias':ssh_alias,
                    'version':manifest['version'],'skill_sha256':skill_sha256,
                    'mcp_sha256':hashlib.sha256((plugin/'.mcp.json').read_bytes()).hexdigest()}
        (stage/'host-registration.json').write_text(json.dumps(metadata,indent=2)+'\n')
        stage.rename(output)
    return output


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    destination = parser.add_mutually_exclusive_group(required=True)
    destination.add_argument('--output', type=Path, help='Fresh plugin directory named luda')
    destination.add_argument('--marketplace-root', type=Path, help='Fresh standalone local marketplace directory')
    parser.add_argument('--prefix', required=True, help='Installed release prefix on the Linux guest')
    parser.add_argument('--user', default='silo-desktop')
    parser.add_argument('--vm-id', help='Host SSH mode: exact VM UUID')
    parser.add_argument('--skill-file', type=Path)
    parser.add_argument('--skill-sha256')
    parser.add_argument('--ssh-config', type=Path)
    parser.add_argument('--ssh-alias')
    parser.add_argument('--ssh-executable', default='/usr/bin/ssh')
    parser.add_argument('--remote', action='store_true', help='Request an available Codex remote executor; host integration must be verified')
    args = parser.parse_args()
    try:
        if args.vm_id:
            if args.remote or not args.marketplace_root or not all((args.skill_file,args.skill_sha256,args.ssh_config,args.ssh_alias)):
                raise ValueError('Host SSH mode requires marketplace-root, skill-file/hash and SSH config/alias; it cannot use remote placement.')
            print(build_host_marketplace(args.marketplace_root,args.prefix,args.vm_id,args.skill_file,args.skill_sha256,args.ssh_config,args.ssh_alias,args.ssh_executable,args.user))
        else:
            if any((args.skill_file,args.skill_sha256,args.ssh_config,args.ssh_alias)):
                raise ValueError('Host SSH arguments require vm-id.')
            builder = build_marketplace if args.marketplace_root else build
            print(builder(args.marketplace_root or args.output, args.prefix, args.user, args.remote))
    except (ValueError, OSError) as exc:
        parser.exit(1, f'{exc}\n')
