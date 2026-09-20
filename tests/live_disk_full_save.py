"""FILE-06: real Mousepad save failure and explicit retry on private 64 KiB tmpfs.

Outer mount setup requires root and a new private mount namespace. All GUI work
runs as the ordinary desktop account in a private Xvfb/D-Bus/XDG session.
"""
import argparse
import errno
import hashlib
import json
import os
from pathlib import Path
import pwd
import subprocess
import sys
import tempfile
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from qualification_matrix import private_environment, run_bounded
from qualify import source_fingerprint


def fixture(storage, output):
    if os.geteuid() == 0 or os.environ.get('LUDA_ISOLATED_TEST_DISPLAY') != '1':
        raise RuntimeError('Ordinary UID and isolated display required')
    wm = subprocess.Popen(['xfwm4', '--compositor=off'])
    editor = None
    results = []
    evidence = {'uid': os.geteuid(), 'results': results}
    def record(name, ok, *, continue_on_failure=False, **detail):
        results.append({'case': name, 'passed': bool(ok), **detail})
        if not continue_on_failure:
            assert ok, name
    try:
        deadline = time.monotonic() + 10
        while subprocess.run(['wmctrl', '-m'], capture_output=True).returncode:
            if time.monotonic() > deadline:
                raise RuntimeError('Window manager unavailable')
            time.sleep(.1)
        import live_file_workflows as files
        files.OUT = output
        storage = Path(storage)
        original = b'Original document must survive.\n'
        target = storage / 'document.txt'
        target.write_bytes(original)
        editor = files.Editor(target)
        text = 'Edited buffer 日本語 👩🏽‍💻\n\tKeep trailing lines.\n\n' * 200
        editor.edit(text)
        filler = storage / 'owned-filler'
        try:
            with filler.open('wb', buffering=0) as stream:
                for _ in range(32):
                    stream.write(b'x' * 4096)
            raise AssertionError('Filesystem is not bounded')
        except OSError as exc:
            record('bounded-filesystem-exhausted', exc.errno == errno.ENOSPC,
                   capacity_bytes=os.statvfs(storage).f_blocks * os.statvfs(storage).f_frsize)
        response = files.d.key(editor.wid, 'ctrl+s')
        evidence['save_dispatch'] = response
        record('input-dispatch-does-not-claim-save-success', response.get('effect') == 'dispatched' and response.get('verification') == 'Key delivery does not prove application outcome.')
        nodes = files.until(lambda: (n if any('space' in x.get('name', '').lower() for x in n) else None)
                            if (n := editor.nodes()) else None)
        evidence['failure_tree'] = nodes
        record('visible-no-space-error', any('no space' in n.get('name', '').lower() for n in nodes))
        after_failure = target.read_bytes()
        (output / 'file-after-failure.bin').write_bytes(after_failure)
        record('failed-save-preserves-original-bytes', after_failure == original,
               continue_on_failure=True, bytes=len(after_failure),
               sha256=hashlib.sha256(after_failure).hexdigest(),
               entries={p.name: p.stat().st_size for p in storage.iterdir()})
        # Close the observed error, not the document. Buffer is read through the
        # public accessibility interface and later proved by exact saved bytes.
        # Mousepad's error alert exposes no AX button. Escape dismisses the
        # active alert; the document's continued existence is checked below.
        files.d.key(editor.active(), 'Escape')
        files.until(lambda: editor.active() == editor.wid)
        node = next(n for n in editor.nodes(editor.wid)
                    if 'EditableText' in n['interfaces'] and 'multi-line' in n['states'])
        buffer = files.d.element(node['element_id'], 'read')
        evidence['buffer_read'] = buffer
        record('failed-save-retains-buffer', buffer.get('text') == text)
        record('failed-save-retains-dirty-document', any(w['window_id'] == editor.wid and '*' in w['title'] for w in editor.windows()))
        filler.unlink()
        files.d.key(editor.wid, 'ctrl+s')
        files.until(lambda: target.read_bytes() == text.encode() or editor.active() != editor.wid)
        evidence['retry_tree'] = editor.nodes()
        evidence['retry_file_bytes'] = target.stat().st_size
        if editor.active() != editor.wid:
            record('retry-external-change-warning-observed', any('externally modified' in n.get('name', '') for n in evidence['retry_tree']))
            # This is our own truncated fixture file; explicitly approve replacing
            # its bytes with the retained buffer, not an arbitrary external change.
            editor.button('Save')
        files.until(lambda: target.read_bytes() == text.encode())
        record('explicit-retry-saves-exact-buffer', target.read_bytes() == text.encode())
        files.until(lambda: any(w['window_id'] == editor.wid and '*' not in w['title'] for w in editor.windows()))
        record('retry-clears-dirty-state', True,
               entries=sorted(p.name for p in storage.iterdir()))
        assert all(r['passed'] for r in results), 'One or more application assertions failed; recovery evidence retained'
    except Exception as exc:
        evidence['error'] = {'type': type(exc).__name__, 'message': str(exc)}
        raise
    finally:
        if editor:
            editor.cleanup()
        if 'files' in locals():
            files.d.close()
        wm.terminate()
        try:
            wm.wait(timeout=3)
        except subprocess.TimeoutExpired:
            wm.kill(); wm.wait(timeout=3)
        evidence['file06_no_successful_save_claim'] = all(any(r['case'] == name and r['passed'] for r in results) for name in ('visible-no-space-error', 'input-dispatch-does-not-claim-save-success'))
        evidence['preservation_diagnostic'] = next((r for r in results if r['case'] == 'failed-save-preserves-original-bytes'), None)
        (output / 'results.json').write_text(json.dumps(evidence, indent=2))


def desktop(storage, output):
    if os.geteuid() == 0:
        raise RuntimeError('GUI runner must not be root')
    before = source_fingerprint(ROOT)
    with tempfile.TemporaryDirectory(prefix='luda-disk-save-session-') as temporary:
        token = uuid.uuid4().hex
        env = private_environment(Path(temporary), token)
        with (output / 'desktop.log').open('wb') as log:
            result = run_bounded(['xvfb-run', '-a', '-s', '-screen 0 1440x1000x24 -nolisten tcp',
                                  'dbus-run-session', '--', sys.executable, __file__,
                                  '--fixture', str(storage), '--output', str(output)], env, log, 90, token)
    after = source_fingerprint(ROOT)
    result.update(source=before, source_after=after, source_unchanged=before == after)
    result['packages'] = subprocess.run(['dpkg-query', '-W', 'mousepad', 'xvfb', 'xfwm4'],
                                        capture_output=True, text=True, timeout=5).stdout
    (output / 'runner.json').write_text(json.dumps(result, indent=2))
    return 0 if result['status'] == 'passed' and before == after else 1


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--namespace', help=argparse.SUPPRESS)
    p.add_argument('--desktop', help=argparse.SUPPRESS)
    p.add_argument('--fixture', help=argparse.SUPPRESS)
    p.add_argument('--output', type=Path)
    p.add_argument('--user', default='silo-desktop')
    args = p.parse_args()
    if args.fixture:
        fixture(args.fixture, args.output)
        return 0
    if args.desktop:
        return desktop(args.desktop, args.output)
    if os.geteuid() != 0:
        p.error('Run outer launcher as root; GUI always drops to --user')
    account = pwd.getpwnam(args.user)
    if account.pw_uid == 0:
        p.error('Desktop account must be non-root')
    if args.namespace:
        if os.readlink('/proc/self/ns/mnt') == args.namespace:
            raise RuntimeError('Refusing mount outside a new private namespace')
        with tempfile.TemporaryDirectory(prefix='luda-disk-save-fs-') as directory:
            subprocess.run(['mount', '-t', 'tmpfs', '-o', 'size=64k,mode=0700', 'tmpfs', directory], check=True)
            try:
                os.chown(directory, account.pw_uid, account.pw_gid)
                return subprocess.call(['runuser', '-u', args.user, '--', sys.executable, __file__,
                                        '--desktop', directory, '--output', str(args.output)])
            finally:
                subprocess.run(['umount', directory], check=True)
    # Shared Editor helper creates this directory on import, then its output
    # is redirected to this invocation's evidence directory.
    (ROOT / 'artifacts/files').mkdir(parents=True, exist_ok=True)
    output = ROOT / 'artifacts/disk-full-save' / str(time.time_ns())
    output.mkdir(parents=True)
    os.chown(output, account.pw_uid, account.pw_gid)
    print('Evidence:', output, flush=True)
    return subprocess.call(['unshare', '--mount', '--propagation', 'private', sys.executable, __file__,
                            '--namespace', os.readlink('/proc/self/ns/mnt'), '--user', args.user,
                            '--output', str(output)])


if __name__ == '__main__':
    raise SystemExit(main())
