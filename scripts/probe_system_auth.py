#!/usr/bin/env python3
"""Read-only system-authentication prerequisites; never prompts or starts services."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess

PACKAGES = ('dbus-daemon', 'polkitd', 'pkexec', 'policykit-1', 'policykit-1-gnome', 'lxpolkit', 'mate-polkit')
PATHS = {
    'polkitd': ('/usr/lib/polkit-1/polkitd', '/usr/libexec/polkitd'),
    'gnome_agent': ('/usr/lib/policykit-1-gnome/polkit-gnome-authentication-agent-1',
                    '/usr/libexec/polkit-gnome-authentication-agent-1'),
    'mate_agent': ('/usr/lib/mate-polkit/polkit-mate-authentication-agent-1',),
}


def probe():
    packages = {}
    for package in PACKAGES:
        query = subprocess.run(['dpkg-query', '-W', '-f=${db:Status-Abbrev}\t${Version}', package],
                               capture_output=True, text=True, timeout=3)
        fields = query.stdout.strip().split('\t', 1)
        packages[package] = {'installed': query.returncode==0 and fields[0].startswith('ii'),
                             'dpkg_status': fields[0] if fields[0] else None,
                             'version': fields[1] if len(fields)>1 and fields[1] else None}
    executables = {name: shutil.which(name) for name in ('pkexec', 'pkttyagent', 'pkaction', 'polkitd', 'lxpolkit')}
    fixed_paths = {kind: {path: Path(path).is_file() and os.access(path, os.X_OK) for path in paths}
                   for kind, paths in PATHS.items()}
    # Only ask the bus daemon for existing names: no authority method, agent
    # registration or implicit activation of org.freedesktop.PolicyKit1.
    system_socket = Path('/run/dbus/system_bus_socket').exists()
    bus = {'standard_socket_exists': system_socket, 'reachable': False}
    if system_socket and shutil.which('gdbus'):
        env = dict(os.environ, DBUS_SYSTEM_BUS_ADDRESS='unix:path=/run/dbus/system_bus_socket')
        query = subprocess.run(['gdbus', 'call', '--system', '--dest', 'org.freedesktop.DBus',
            '--object-path', '/org/freedesktop/DBus', '--method', 'org.freedesktop.DBus.ListNames'],
            env=env, capture_output=True, text=True, timeout=3)
        bus.update(reachable=query.returncode==0,
                   authority_name_present=query.returncode==0 and "'org.freedesktop.PolicyKit1'" in query.stdout)
        # Do not retain unrelated service names or error payloads.
        bus['list_names_returncode'] = query.returncode
    processes = []
    for directory in Path('/proc').iterdir():
        if not directory.name.isdigit(): continue
        try:
            name = (directory/'comm').read_text().strip()
            if any(part in name.lower() for part in ('polkit', 'policykit', 'logind')):
                processes.append({'pid': int(directory.name), 'uid': directory.stat().st_uid, 'comm': name})
        except (OSError, ProcessLookupError): pass
    policies = Path('/usr/share/polkit-1/actions')
    policy_files = sorted(str(path) for path in policies.glob('*.policy') if path.is_file()) if policies.is_dir() else []
    blockers = []
    if not system_socket: blockers.append('Standard system D-Bus socket is absent.')
    elif not bus['reachable']: blockers.append('Standard system D-Bus cannot be queried by this account.')
    if not packages['polkitd']['installed'] and not executables['polkitd'] and not any(fixed_paths['polkitd'].values()):
        blockers.append('No installed polkit authority found in the checked package/executable locations.')
    if not executables['pkexec']: blockers.append('pkexec executable is unavailable on PATH.')
    if not any(any(paths.values()) for kind, paths in fixed_paths.items() if kind.endswith('_agent')) and not executables['lxpolkit']:
        blockers.append('No graphical authentication agent found in the checked locations.')
    return {'probe': 'system-authentication-prerequisites', 'timestamp_utc': datetime.now(timezone.utc).isoformat(),
            'uid': os.getuid(), 'platform': platform.platform(), 'pid1_comm': Path('/proc/1/comm').read_text().strip(),
            'status': 'blocked' if blockers else 'prerequisites_found_not_qualified', 'blockers': blockers,
            'packages': packages, 'executables': executables, 'fixed_executable_locations': fixed_paths,
            'system_bus': bus, 'matching_processes': processes, 'policy_filenames_only': policy_files,
            'authentication_requests': 0, 'gui_input_events': 0, 'policy_or_session_changes': 0,
            'limits': ['Known distro locations and standard system bus only; custom installations may differ.',
                       'Prerequisite discovery cannot qualify dialog identity, privileged-operation notice, cancellation or caller outcome.']}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = probe()
    text = json.dumps(result, indent=2)+'\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    print(text, end='')
    raise SystemExit(2 if result['status']=='blocked' else 0)


if __name__=='__main__': main()
