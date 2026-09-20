#!/usr/bin/env python3
"""Opt-in add-on GUI qualification; requires core and editor bridge installed."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'scripts'))
import qualification_matrix as matrix
from qualification_matrix import suite
# Bind optional runtime, application adapter, skill and tests as well as core.
# The core source fingerprint deliberately excludes separately installed add-ons.
import hashlib
import json
core_fingerprint = matrix.source_fingerprint

def source_fingerprint(root):
    files = dict(core_fingerprint(root)['files'])
    addon = root/'addons/editor-bridge'
    for folder in ('src','application','skills','tests','scripts','docs','.codex-plugin'):
        for path in (addon/folder).rglob('*'):
            if not path.is_file() or any(part in ('node_modules','__pycache__','build','dist') or part.endswith('.egg-info') for part in path.parts) or path.suffix in ('.pyc','.pyo'):
                continue
            files[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    for name in ('pyproject.toml','MANIFEST.in','README.md','LICENSE','.mcp.json'):
        path=addon/name
        if path.is_file():files[str(path.relative_to(root))]=hashlib.sha256(path.read_bytes()).hexdigest()
    return {'sha256':hashlib.sha256(json.dumps(files,sort_keys=True).encode()).hexdigest(),'files':files}

matrix.source_fingerprint = source_fingerprint

matrix.SUITES = {
    'rich-progress': suite('../addons/editor-bridge/tests/live_rich_progress.py', 'ERR-05', browser='--executable', artifacts=('rich-progress',), gaps=('Final error receipt after one verified rich segment and a rejected paragraph action; not lost-receipt cancellation progress',)),
    'owned-rich-clipboard': suite('../addons/editor-bridge/tests/live_owned_rich_clipboard.py', 'WEB-03 DATA-07', browser='--executable', artifacts=('owned-rich-clipboard',), gaps=('Explicit clipboard transport; cooperating basic ProseMirror only',), timeout=300),
    'owned-hard-breaks': suite('../addons/editor-bridge/tests/live_owned_hard_breaks.py', 'DATA-07 WEB-03', browser='--executable', artifacts=('owned-hard-breaks',), gaps=('Explicit cooperating ProseMirror hard-break schema; not generic rich editors',)),
    'owned-rich': suite('../addons/editor-bridge/tests/live_owned_rich.py', 'WEB-03 DATA-07', browser='--executable', artifacts=('owned-rich',), gaps=('Cooperating basic ProseMirror paragraphs only; not arbitrary rich editors',)),
}

if __name__ == "__main__":
    raise SystemExit(matrix.main(entrypoint=Path(__file__).resolve()))
