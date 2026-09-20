#!/usr/bin/env python3
"""Execute patched upstream Silo sources; never substitute a native module stub."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location('silo_apply', ROOT/'integrations/silo/apply.py')
patches = importlib.util.module_from_spec(spec)
spec.loader.exec_module(patches)


def commands(checkout):
    return [
        ('frontend', ['node_modules/.bin/vitest', 'run', 'src/desktop/codex-desktop-registration.test.tsx', 'src/desktop/linux-desktop-native.test.tsx', 'src/desktop/linux-desktop-viewer.test.tsx', '--maxWorkers=2']),
        ('typescript', ['node_modules/.bin/tsc', '-b', '--pretty', 'false']),
        ('native', ['cargo', 'test', '--manifest-path', str(checkout/'app/SiloUI/src-tauri/Cargo.toml'), '--locked', 'codex_desktop::tests', '--', '--include-ignored', '--test-threads=1']),
    ]


def native_complete(text):
    return bool(re.search(r'test result: ok\. 10 passed; 0 failed; 0 ignored;', text)) and all(
        re.search(r'test codex_desktop::tests::'+name+r' \.\.\. ok', text)
        for name in ('actual_cli_registration_and_removal_reconcile_without_replay',
                     'actual_cli_recovery_repairs_only_proven_source_and_receipt_without_install_replay',
                     'actual_cli_reviewed_update_preserves_other_vm_and_records_uncertainty',
                     'actual_cli_failed_removal_is_not_replayed',
                     'actual_cli_two_vm_configuration_and_idempotency'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('checkout', type=Path, help='Clean pinned Silo checkout; patches will be applied')
    parser.add_argument('--codex', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    checkout, output = args.checkout.resolve(), args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = {'passed': False, 'silo_base': patches.BASE, 'steps': [], 'scope': 'Actual patched Silo Rust module and real Codex CLI; frontend Tauri calls mocked. No packaged runtime, Mac, SSH connectivity or VM acceptance.'}
    try:
        version = subprocess.check_output([str(args.codex.resolve()), '--version'], text=True, timeout=10).strip()
        if version != 'codex-cli 0.155.1':
            raise ValueError('Require locked Codex CLI 0.155.1')
        report['codex_version'] = version
        report['patches'] = {name: hashlib.sha256((patches.ASSETS/name).read_bytes()).hexdigest() for name in patches.PATCHES}
        patches.apply(checkout, True)
        env = dict(os.environ, SILO_TEST_CODEX=str(args.codex.resolve()), SILO_GITHUB_APP_SLUG='silo-linux-test', SILO_GITHUB_CLIENT_ID='test-client', SILO_GITHUB_CLIENT_SECRET='test-secret', CARGO_PROFILE_DEV_DEBUG='0', CARGO_PROFILE_TEST_DEBUG='0', CARGO_INCREMENTAL='0', CARGO_BUILD_JOBS='2', TAURI_CONFIG='{"bundle":{"externalBin":[],"resources":[]}}')
        for name, argv in [('dependencies', ['npm', 'ci', '--no-audit', '--no-fund'])] + commands(checkout):
            with (output/(name+'.log')).open('w') as log:
                result = subprocess.run(argv, cwd=checkout/'app/SiloUI', env=env, stdout=log, stderr=subprocess.STDOUT, timeout=3600)
            report['steps'].append({'name': name, 'argv': argv, 'exit_code': result.returncode})
            if result.returncode:
                raise ValueError('Step failed: '+name)
            if name == 'native' and not native_complete((output/'native.log').read_text()):
                raise ValueError('Expected all ten native cases, including five actual CLI cases, without skips')
        report['passed'] = True
    except (ValueError, OSError, subprocess.SubprocessError) as exc:
        report['failure'] = str(exc)
    finally:
        (output/'result.json').write_text(json.dumps(report, indent=2)+'\n')
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
