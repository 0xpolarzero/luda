#!/usr/bin/env python3
"""Check (or explicitly apply) the Luda integration to the pinned Silo checkout."""
import argparse
from pathlib import Path
import subprocess

BASE = '777e1090d5e998059758160912138228ba98378d'
ASSETS = Path(__file__).resolve().parent


def apply(checkout, mutate=False):
    def git(*args):
        return subprocess.run(['git', '-C', str(checkout), *args], capture_output=True, text=True)
    head = git('rev-parse', 'HEAD')
    if head.returncode or head.stdout.strip() != BASE:
        raise ValueError('Require the exact pinned Silo base commit.')
    if git('diff', '--quiet', 'HEAD', '--').returncode:
        raise ValueError('Require a checkout with no tracked changes.')
    patches = [str(ASSETS / name) for name in ('0001-guest-onboarding.patch', '0002-desktop-onboarding.patch', '0003-host-codex-registration.patch')]
    if git('apply', '--check', *patches).returncode:
        raise ValueError('Patch check failed; preserve existing files and inspect the checkout.')
    if mutate and git('apply', *patches).returncode:
        raise ValueError('Patch application failed; inspect the checkout before retrying.')
    return 'Applied all three patches.' if mutate else 'All three patches apply cleanly; no files changed.'


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
