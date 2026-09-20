#!/usr/bin/env python3
"""Fail closed on CI browser/version drift; emit explicit provisioning evidence."""
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import subprocess

PLAYWRIGHT = '1.63.0'
REVISION = '1243'
BROWSER_VERSION = '153.0.8010.12'


def profile(executable):
    # This CI attachment is one exact executable, never a broad directory glob.
    if not re.fullmatch(r'/[A-Za-z0-9_./-]+', executable):
        raise ValueError('CI executable path cannot be represented safely in the exact AppArmor attachment')
    return ('abi <abi/4.0>,\ninclude <tunables/global>\n'
            f'profile luda-ci-owned-browser "{executable}" flags=(unconfined) {{\n  userns,\n}}\n')


def main():
    if os.geteuid()==0:
        raise SystemExit('CI browser qualification must run as an ordinary account')
    import playwright
    from playwright.sync_api import sync_playwright
    if importlib.metadata.version('playwright') != PLAYWRIGHT:
        raise SystemExit('Unexpected Playwright version; update pins and qualify deliberately')
    manifest=json.loads((Path(playwright.__file__).parent/'driver/package/browsers.json').read_text())
    chromium=next(item for item in manifest['browsers'] if item['name']=='chromium')
    if chromium['revision']!=REVISION or chromium['browserVersion']!=BROWSER_VERSION:
        raise SystemExit('Unexpected Playwright Chromium revision or version')
    with sync_playwright() as engine:
        executable=Path(engine.chromium.executable_path).resolve(strict=True)
    version=subprocess.run([str(executable),'--version'],check=True,capture_output=True,text=True,timeout=5).stdout.strip()
    if version.split()[-1]!=BROWSER_VERSION:
        raise SystemExit('Provisioned Chromium executable version differs from pinned manifest')
    output=Path('artifacts/owned-browser-provision');output.mkdir(parents=True,exist_ok=True)
    (output/'browser-path.txt').write_text(str(executable)+'\n')
    (output/'apparmor.profile').write_text(profile(str(executable)))
    (output/'environment.json').write_text(json.dumps({'uid':os.getuid(),'architecture':platform.machine(),'playwright':PLAYWRIGHT,
        'chromium_revision':REVISION,'browser_version':version,'executable':str(executable),'sandbox_requested':True,
        'runtime_downloads':False,'provisioning':'explicit CI-only Playwright install; actual launch and effects checked separately by matrix'},indent=2)+'\n')


if __name__=='__main__':main()
