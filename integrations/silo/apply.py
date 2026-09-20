#!/usr/bin/env python3
"""Check (or explicitly apply) the Luda integration to the pinned Silo checkout."""
import argparse
from pathlib import Path
import subprocess
import os
import tempfile

BASE = '777e1090d5e998059758160912138228ba98378d'
ASSETS = Path(__file__).resolve().parent
PATCHES = ('0001-guest-onboarding.patch', '0002-desktop-onboarding.patch',
           '0003-host-codex-registration.patch', '0004-preserve-registered-transport.patch',
           '0005-refresh-agent-skill.patch', '0006-host-registration-lifecycle.patch',
           '0007-reviewed-version-update.patch', '0008-native-ssh-qualification.patch',
           '0009-bound-keygen-capture.patch', '0010-refresh-recording-skill.patch',
           '0011-inspect-update-recovery.patch', '0012-refresh-matching-skill.patch',
           '0013-reconcile-registration-state.patch',
           '0014-refresh-browser-skill.patch',
           '0015-registration-panel-layout.patch',
           '0016-refresh-rich-browser-skill.patch',
           '0017-refresh-text-boundary-skill.patch',
           '0018-managed-browser-onboarding.patch',
           '0019-browser-completion-status.patch',
           '0020-refresh-rich-clipboard-skill.patch',
           '0021-refresh-selection-focus-skill.patch')


def apply(checkout, mutate=False):
    def git(*args, **kwargs):
        return subprocess.run(['git', '-C', str(checkout), *args], capture_output=True, text=True, **kwargs)
    head = git('rev-parse', 'HEAD')
    if head.returncode or head.stdout.strip() != BASE:
        raise ValueError('Require the exact pinned Silo base commit.')
    if git('diff', '--quiet', 'HEAD', '--').returncode:
        raise ValueError('Require a checkout with no tracked changes.')
    patches = [str(ASSETS / name) for name in PATCHES]
    # An ordered patch can modify a file added by an earlier patch. Build the
    # complete result in an isolated index before touching the user's checkout.
    with tempfile.TemporaryDirectory(prefix='luda-silo-index-') as temporary:
        env = dict(os.environ, GIT_INDEX_FILE=str(Path(temporary) / 'index'))
        if git('read-tree', 'HEAD', env=env).returncode:
            raise ValueError('Unable to prepare isolated patch check.')
        for patch in patches:
            if git('apply', '--cached', patch, env=env).returncode:
                raise ValueError('Patch check failed; preserve existing files and inspect the checkout.')
        combined = git('diff', '--cached', '--binary', 'HEAD', env=env)
        if combined.returncode or git('apply', '--check', '-', input=combined.stdout).returncode:
            raise ValueError('Patch check failed; preserve existing files and inspect the checkout.')
        if mutate and git('apply', '-', input=combined.stdout).returncode:
            raise ValueError('Patch application failed; inspect the checkout before retrying.')
    return f'Applied {len(PATCHES)} integration patches.' if mutate else f'All {len(PATCHES)} integration patches apply cleanly; no files changed.'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('checkout', type=Path)
    parser.add_argument('--apply', action='store_true', help='Actually modify the supplied pinned checkout')
    args = parser.parse_args()
    try:
        print(apply(args.checkout, args.apply))
    except ValueError as exc:
        parser.exit(1, str(exc) + '\n')


if __name__ == '__main__':
    main()
