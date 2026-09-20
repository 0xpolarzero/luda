"""Owned Mousepad Save As symlink/renamed paths; independent filesystem oracles."""
import json
import os
from pathlib import Path
import tempfile
import live_file_workflows as files

OUT = Path(__file__).resolve().parents[1] / 'artifacts/file-destinations'
OUT.mkdir(parents=True, exist_ok=True)
files.OUT = OUT


def symlink(root):
    source = root / 'source.txt'
    target = root / 'actual 日本語.txt'
    link = root / 'visible-link.txt'
    source.write_text('source\n')
    target.write_text('original target\n')
    link.symlink_to(target.name)
    editor = files.Editor(source)
    value = 'symlink destination\n日本語 👩🏽‍💻\n\n'
    try:
        editor.edit(value)
        editor.save_as(link)
        editor.button('Replace')
        files.until(lambda: link.read_text() == value)
        actual = {'case': 'save-as-symlink-result', 'link_is_symlink': link.is_symlink(),
                  'requested_path': link.name, 'resolved_path': link.resolve().name,
                  'referent_changed': target.read_text() == value,
                  'requested_exact': link.read_text() == value}
        files.results.append(actual)
        files.record('save-as-symlink-follows-target-preserves-link', link.is_symlink() and target.read_text() == value and source.read_text() == 'source\n')
    finally:
        editor.cleanup()


def renamed(root):
    source = root / 'before-rename.txt'
    destination = root / 'renamed 日本語.txt'
    source.write_text('original\n')
    editor = files.Editor(source)
    value = 'renamed destination\n日本語 👩🏽‍💻\n'
    try:
        # Independent external actor renames this suite-owned file while open.
        source.rename(destination)
        editor.edit(value)
        editor.save_as(destination)
        editor.button('Replace')
        files.until(lambda: destination.read_text() == value)
        files.record('renamed-explicit-save-as-writes-actual-new-path', destination.read_text() == value and not source.exists())
        value += 'second save\n'
        editor.edit(value)
        files.d.key(editor.wid, 'ctrl+s')
        files.until(lambda: destination.read_text() == value)
        files.record('subsequent-save-does-not-recreate-old-name', destination.read_text() == value and not source.exists())
    finally:
        editor.cleanup()


if __name__ == '__main__':
    if os.geteuid() == 0 or os.environ.get('LUDA_ISOLATED_TEST_DISPLAY') != '1':
        raise SystemExit('Use an ordinary UID and private X11/D-Bus/XDG session.')
    try:
        with tempfile.TemporaryDirectory(prefix='luda-file-destinations-') as directory:
            root = Path(directory)
            symlink(root)
            renamed(root)
    except Exception as exc:
        files.results.append({'case': 'suite-completion', 'passed': False, 'error_type': type(exc).__name__})
        raise
    finally:
        files.d.close()
        (OUT / 'results.json').write_text(json.dumps(files.results, indent=2) + '\n')
        print(json.dumps(files.results), flush=True)
