#!/usr/bin/env python3
"""Opt-in add-on GUI qualification; requires core and editor bridge installed."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'scripts'))
import qualification_matrix as matrix
from qualification_matrix import suite
matrix.SUITES = {
    'rich-progress': suite('../addons/editor-bridge/tests/live_rich_progress.py', 'ERR-05', browser='--executable', artifacts=('rich-progress',), gaps=('Final error receipt after one verified rich segment and a rejected paragraph action; not lost-receipt cancellation progress',)),
    'owned-rich-clipboard': suite('../addons/editor-bridge/tests/live_owned_rich_clipboard.py', 'WEB-03 DATA-07', browser='--executable', artifacts=('owned-rich-clipboard',), gaps=('Explicit clipboard transport; cooperating basic ProseMirror only',), timeout=300),
    'owned-hard-breaks': suite('../addons/editor-bridge/tests/live_owned_hard_breaks.py', 'DATA-07 WEB-03', browser='--executable', artifacts=('owned-hard-breaks',), gaps=('Explicit cooperating ProseMirror hard-break schema; not generic rich editors',)),
    'owned-rich': suite('../addons/editor-bridge/tests/live_owned_rich.py', 'WEB-03 DATA-07', browser='--executable', artifacts=('owned-rich',), gaps=('Cooperating basic ProseMirror paragraphs only; not arbitrary rich editors',)),
}

if __name__ == "__main__":
    raise SystemExit(matrix.main(entrypoint=Path(__file__).resolve()))
