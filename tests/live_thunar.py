"""Owned, offline Thunar UI operations with independent filesystem oracles.

Run as an ordinary user in an isolated Xvfb/D-Bus session with private XDG
config/data/cache directories established before starting the session bus.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

from luda.desktop import Desktop

OUT = Path(__file__).resolve().parents[1] / 'artifacts/thunar'
OUT.mkdir(parents=True, exist_ok=True)
results = []


def until(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(.08)
    raise AssertionError('Expected UI/filesystem transition did not occur')


def record(name, passed):
    results.append({'case': name, 'passed': bool(passed)})
    assert passed, name


def run(root):
    source = root / 'source'
    destination = root / 'destination'
    folders = root / 'folders'
    for path in (source, destination, folders):
        path.mkdir()
    payload = b'owned binary payload\x00\xff\n' + '日本語 👩🏽‍💻'.encode()
    original = source / 'copy 日本語.bin'
    original.write_bytes(payload)
    d = Desktop()
    p = subprocess.Popen(['thunar', str(folders)], env={**os.environ, 'GSETTINGS_BACKEND': 'memory'})
    try:
        def windows():
            return [w for w in d.list_windows() if w['pid'] == p.pid]
        def active():
            return until(lambda: next((w['window_id'] for w in windows() if w['active']), None))
        wid = until(lambda: next((w['window_id'] for w in windows()), None))
        d.activate(wid)
        def nodes():
            tree = d.inspect(active())
            (OUT / 'last-tree.json').write_text(json.dumps(tree, indent=2))
            return tree['nodes']
        def button(name):
            node = until(lambda: next((n for n in nodes() if n['role'] == 'push button' and n['name'].replace('_', '') == name and 'showing' in n['states']), None))
            d.element(node['element_id'], 'invoke', action=node['actions'][0])
        def confirmation(label):
            until(lambda: any(label in n.get('name', '') for n in nodes()))
        def entry(value):
            node = until(lambda: next((n for n in nodes() if 'EditableText' in n['interfaces'] and 'showing' in n['states'] and 'single-line' in n['states']), None))
            d.type_text(node['element_id'], value, mode='replace')
        def key(chord):
            d.key(active(), chord)
        def main():
            until(lambda: active() == wid)
        def navigate(path):
            main()
            key('ctrl+l')
            entry(str(path))
            key('Return')
            until(lambda: any(str(path) == n.get('text', '') for n in nodes()) or any(path.name in w['title'] for w in windows()))
            # Observe a fresh directory tree before selecting its entries.
            nodes()
        key('ctrl+shift+n')
        until(lambda: active() != wid)
        entry('cancelled folder')
        button('Cancel')
        main()
        record('create-folder-cancel', not (folders / 'cancelled folder').exists())
        key('ctrl+shift+n')
        until(lambda: active() != wid)
        entry('new 日本語')
        button('Create')
        until(lambda: (folders / 'new 日本語').is_dir())
        record('create-folder-unicode', (folders / 'new 日本語').is_dir())
        main()
        key('ctrl+a')
        key('F2')
        until(lambda: active() != wid)
        entry('cancelled rename')
        button('Cancel')
        main()
        record('rename-cancel', (folders / 'new 日本語').is_dir() and not (folders / 'cancelled rename').exists())
        key('F2')
        until(lambda: active() != wid)
        entry('renamed 日本語')
        button('Rename')
        until(lambda: (folders / 'renamed 日本語').is_dir())
        record('rename-folder', not (folders / 'new 日本語').exists())
        navigate(source)
        key('ctrl+a')
        key('ctrl+c')
        navigate(destination)
        key('ctrl+v')
        copied = destination / original.name
        until(lambda: copied.exists())
        record('copy-paste-binary-exact', copied.read_bytes() == payload and original.read_bytes() == payload)
        # Independent setup for a real overwrite conflict; paste remains UI-driven.
        copied.write_bytes(b'preserve conflicting file')
        key('ctrl+v')
        until(lambda: active() != wid)
        confirmation('Replace')
        button('Cancel')
        main()
        record('copy-conflict-cancel', copied.read_bytes() == b'preserve conflicting file' and original.read_bytes() == payload)
        key('ctrl+v')
        until(lambda: active() != wid)
        button('Replace')
        until(lambda: copied.read_bytes() == payload)
        record('copy-conflict-explicit-replace', original.read_bytes() == payload)
        main()
        key('ctrl+a')
        key('shift+Delete')
        until(lambda: active() != wid)
        confirmation('permanently delete')
        button('Cancel')
        main()
        record('permanent-delete-cancel', copied.read_bytes() == payload)
        key('shift+Delete')
        until(lambda: active() != wid)
        confirmation('permanently delete')
        button('Delete')
        until(lambda: not copied.exists())
        record('permanent-delete-confirmed', original.read_bytes() == payload)
    finally:
        if p.poll() is None:
            p.terminate()
            p.wait(timeout=5)
        d.close()


if __name__ == '__main__':
    if os.geteuid() == 0:
        raise SystemExit('Run in a private desktop session as an ordinary user.')
    try:
        with tempfile.TemporaryDirectory(prefix='luda-owned-thunar-') as directory:
            run(Path(directory))
    except Exception as exc:
        results.append({'case': 'suite-completion', 'passed': False, 'error_type': type(exc).__name__})
        raise
    finally:
        (OUT / 'results.json').write_text(json.dumps(results, indent=2))
        print(json.dumps(results))
