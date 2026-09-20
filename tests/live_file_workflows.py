"""Mousepad native file workflows, owned fixtures and independent disk oracles.

Run as a non-root user in an isolated X11/D-Bus desktop (or hold the shared
GUI lease for the entire invocation). Does not operate on preexisting apps.
"""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time

from luda.desktop import Desktop
from luda.common import DesktopError
from window_oracles import application_target

OUT = Path(__file__).resolve().parents[1] / 'artifacts/files' / f'run-{time.time_ns()}'
OUT.mkdir(parents=True, exist_ok=True)
results = []
d = Desktop()


def until(predicate, seconds=5):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        value = predicate()
        if value:
            return value
        time.sleep(.06)
    raise AssertionError('condition did not become true')


def record(name, ok):
    results.append({'case': name, 'passed': bool(ok)})
    assert ok, name


class Editor:
    def __init__(self, path):
        self.p = subprocess.Popen(['mousepad', '--disable-server', str(path)],
                                  env={**os.environ, 'GSETTINGS_BACKEND': 'memory'})
        try:
            # Window-manager focus-stealing policy need not auto-activate a new app.
            # Observe one owned window first, then explicitly request activation.
            def sole_owned_window():
                windows = self.windows()
                (OUT / 'startup-windows.json').write_text(json.dumps(windows, indent=2))
                return windows[0]['window_id'] if len(windows) == 1 else None
            self.wid = until(sole_owned_window)
            d.activate(self.wid)
            until(lambda: self.nodes(self.wid))
        except Exception:
            self.cleanup()
            raise

    def windows(self):
        return [w for w in d.list_windows() if w['pid'] == self.p.pid]

    def nodes(self, wid=None):
        wid = wid or self.active()
        tree = d.inspect(wid)
        (OUT / 'last-tree.json').write_text(json.dumps(tree, indent=2))
        return tree['nodes']

    def active(self):
        def selected():
            windows = self.windows()
            (OUT / 'last-windows.json').write_text(json.dumps(windows, indent=2))
            return application_target(windows, self.wid)
        return until(selected)

    def edit(self, value):
        node = until(lambda: next((n for n in self.nodes(self.wid) if 'EditableText' in n['interfaces'] and 'multi-line' in n['states']), None))
        d.element(node['element_id'], 'set', text=value)
        d.element(node['element_id'], 'focus')

    def button(self, name):
        node = until(lambda: next((n for n in self.nodes() if n['role'] == 'push button' and n['name'].replace('_', '') == name and 'showing' in n['states']), None))
        d.element(node['element_id'], 'invoke', action=node['actions'][0])

    def save_as(self, path):
        d.key(self.wid, 'ctrl+shift+s')
        until(lambda: self.active() != self.wid)
        node = until(lambda: next((n for n in self.nodes() if 'EditableText' in n['interfaces'] and 'single-line' in n['states'] and 'showing' in n['states']), None))
        d.element(node['element_id'], 'set', text=str(path))
        self.button('Save')

    def close_request(self):
        d.key(self.wid, 'ctrl+w')
        until(lambda: self.active() != self.wid)

    def cleanup(self):
        if self.p.poll() is None:
            self.p.terminate()
            self.p.wait(timeout=5)


def overwrite(root):
    original = root / 'original.txt'
    target = root / 'existing 日本語.txt'
    original.write_text('source\n')
    target.write_text('preserve me\n')
    e = Editor(original)
    try:
        value = 'replacement\n日本語 👩🏽‍💻\n\n'
        e.edit(value)
        e.save_as(target)
        until(lambda: any(n['role'] == 'push button' and n['name'] == 'Replace' for n in e.nodes()))
        e.button('Cancel')
        record('overwrite-cancel-preserves-existing-bytes', target.read_bytes() == b'preserve me\n')
        # GTK's overwrite Cancel returns to Save As; cancel that chooser too.
        until(lambda: not any(n['name'] == 'Replace' for n in e.nodes()))
        if e.active() != e.wid:
            e.button('Cancel')
        until(lambda: e.active() == e.wid)
        e.cleanup()
        e = Editor(original)
        e.edit(value)
        e.save_as(target)
        e.button('Replace')
        until(lambda: target.read_text() == value)
        record('overwrite-explicit-replace-exact', target.read_text() == value and original.read_bytes() == b'source\n')
    finally:
        e.cleanup()


def unsaved(root, choice):
    path = root / (choice + '.txt')
    path.write_text('original\n')
    e = Editor(path)
    try:
        value = 'unsaved change 日本語\n'
        e.edit(value)
        e.close_request()
        record('unsaved-' + choice + '-dialog-is-not-close', any(w['window_id'] == e.wid for w in e.windows()) and path.read_bytes() == b'original\n')
        e.button(choice)
        if choice == 'Cancel':
            until(lambda: e.active() == e.wid)
            record('unsaved-cancel-keeps-document', bool(e.windows()) and path.read_bytes() == b'original\n')
            # Saving proves cancellation also preserved the actual edited buffer.
            d.key(e.wid, 'ctrl+s')
            until(lambda: path.read_text() == value)
            record('unsaved-cancel-retains-edits', path.read_text() == value)
        else:
            until(lambda: not any(w['window_id'] == e.wid for w in e.windows()))
            record('unsaved-' + choice + '-closes-after-decision', path.read_text() == (value if choice == 'Save' else 'original\n'))
    finally:
        e.cleanup()


def readonly(root):
    source = root / 'readonly-source.txt'
    folder = root / 'locked'
    folder.mkdir()
    target = folder / 'existing.txt'
    source.write_text('source\n')
    target.write_text('protected\n')
    target.chmod(0o444)
    folder.chmod(0o555)
    e = Editor(source)
    try:
        e.edit('must not replace\n')
        e.save_as(target)
        e.button('Replace')
        # The error must be observed, not inferred from unchanged bytes alone.
        def permission_error_visible():
            try:
                nodes = e.nodes()
            except DesktopError as exc:
                # The chooser/overwrite alert disappears before its replacement
                # error is registered on AT-SPI. Retry only this read-only probe;
                # the Replace action above is never replayed.
                if exc.code in ('ACCESSIBILITY_UNAVAILABLE', 'STALE_TARGET') and exc.effect == 'none':
                    return False
                raise
            return any(any(word in n.get('name', '').lower()
                           for word in ('permission', 'denied', 'read-only')) for n in nodes)
        until(permission_error_visible)
        record('readonly-save-refusal-preserves-bytes', target.read_bytes() == b'protected\n' and source.read_bytes() == b'source\n')
    finally:
        e.cleanup()
        folder.chmod(0o755)
        target.chmod(0o644)


if __name__ == '__main__':
    if os.geteuid() == 0:
        raise SystemExit('Run as an ordinary user: root bypasses read-only permissions.')
    try:
        with tempfile.TemporaryDirectory(prefix='luda-owned-files-') as directory:
            root = Path(directory)
            for variable, suffix in [('XDG_CONFIG_HOME', 'config'), ('XDG_DATA_HOME', 'data'), ('XDG_CACHE_HOME', 'cache')]:
                os.environ[variable] = str(root / suffix)
            overwrite(root)
            for choice in ("Cancel", "Don't Save", "Save"):
                unsaved(root, choice)
            readonly(root)
    except Exception as exc:
        results.append({'case': 'suite-completion', 'passed': False, 'error_type': type(exc).__name__})
        raise
    finally:
        d.close()
        (OUT / 'results.json').write_text(json.dumps(results, indent=2))
        print(json.dumps(results))
