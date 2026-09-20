#!/usr/bin/env python3
"""Test an extracted distro sshd configuration without opening a listener."""
import argparse
import json
import os
from pathlib import Path
import pwd
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--package-root', type=Path, required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    base = args.package_root.resolve()
    # Only the private extracted binaries/libraries and newly generated host key
    # are used. No default SSH config, known-hosts or identity key is consulted.
    ssh = base/'usr/bin/ssh'; keygen = base/'usr/bin/ssh-keygen'; sshd = base/'usr/sbin/sshd'
    if not all(path.is_file() for path in (ssh, keygen, sshd)):
        parser.error('Extract official openssh-client/server packages into --package-root first.')
    libraries = [str(path) for path in (base/'usr/lib').glob('*-linux-gnu') if path.is_dir()]
    env = dict(os.environ, LD_LIBRARY_PATH=':'.join(libraries))
    identity = pwd.getpwuid(os.getuid())
    try:
        account = pwd.getpwnam('sshd'); privsep = {'present': True, 'uid': account.pw_uid, 'gid': account.pw_gid}
    except KeyError:
        privsep = {'present': False}
    version = subprocess.run([str(ssh), '-V'], env=env, capture_output=True, text=True, timeout=3)
    dependencies = subprocess.run(['ldd', str(sshd)], env=env, capture_output=True, text=True, timeout=3)
    with tempfile.TemporaryDirectory(prefix='luda-private-ssh-config-') as directory:
        root = Path(directory); hostkey = root/'hostkey'; authorized = root/'authorized_keys'; authorized.touch(mode=0o600)
        subprocess.run([str(keygen), '-q', '-t', 'ed25519', '-N', '', '-f', str(hostkey)],
                       env=env, check=True, capture_output=True, timeout=5)
        config = root/'sshd_config'
        config.write_text('\n'.join([
            'Port 22999', 'ListenAddress 127.0.0.1', 'AddressFamily inet',
            f'HostKey {hostkey}', f'PidFile {root / "sshd.pid"}',
            f'AuthorizedKeysFile {authorized}', 'UsePAM no', 'PasswordAuthentication no',
            'KbdInteractiveAuthentication no', 'PermitRootLogin no', 'PubkeyAuthentication yes',
            'StrictModes yes', f'AllowUsers {identity.pw_name}', 'AllowTcpForwarding no',
            'AllowAgentForwarding no', 'X11Forwarding no', 'PermitTunnel no', 'PermitUserRC no',
        ])+'\n')
        checked = subprocess.run([str(sshd), '-t', '-f', str(config)],
                                 env=env, capture_output=True, text=True, timeout=5)
        # Diagnostic filenames are ephemeral test paths, never secret key data.
        diagnostic = checked.stderr.replace(directory, '<private-test-directory>').strip()
    result = {'probe': 'extracted-openssh-config-only', 'uid': os.getuid(),
              'version': (version.stdout+version.stderr).strip(), 'privilege_separation_account': privsep,
              'privilege_separation_directory_exists': Path('/run/sshd').exists(),
              'unresolved_libraries': [line.strip() for line in dependencies.stdout.splitlines() if 'not found' in line],
              'sshd_config_test_returncode': checked.returncode, 'diagnostic': diagnostic,
              'status': 'blocked' if checked.returncode else 'config_valid_not_transport_qualified',
              'listeners_started': 0, 'authentication_attempts': 0,
              'existing_keys_read': 0, 'global_account_or_auth_changes': 0,
              'limits': ['Config-only validation cannot qualify authentication, MCP transport loss or remote input cleanup.']}
    text = json.dumps(result, indent=2)+'\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(text)
    print(text, end='')
    raise SystemExit(2 if result['status']=='blocked' else 0)


if __name__=='__main__': main()
