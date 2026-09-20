"""Actual ENOSPC/EROFS in a private 64 KiB tmpfs, never the host filesystem."""
import argparse
import errno
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import Mock, patch

from luda.common import DesktopError
from luda.desktop import Desktop


def inside(parent_namespace):
    if os.readlink('/proc/self/ns/mnt') == parent_namespace:
        raise SystemExit('Refusing mounts outside a new private mount namespace.')
    results = []
    def record(case, passed):
        results.append({'case': case, 'passed': bool(passed)})
        assert passed, results[-1]
    with tempfile.TemporaryDirectory(prefix='luda-private-storage-') as directory:
        root = Path(directory)
        subprocess.run(['mount', '-t', 'tmpfs', '-o', 'size=64k,mode=0700', 'tmpfs', str(root)], check=True)
        d = Desktop()
        d.runtime = root
        d.x = Mock()
        d.x.root = 1
        d.x.geometry.return_value = {'width': 100, 'height': 100}
        d.list_windows = Mock(return_value=[])
        d.observe_popups = Mock(return_value=[])
        d.target_window = Mock(return_value={'wm_class': []})
        d.key = Mock()
        try:
            filler = root / 'bounded-filler'
            try:
                with filler.open('wb', buffering=0) as stream:
                    for _ in range(32):
                        stream.write(b'x' * 4096)
                raise AssertionError('64KiB filesystem did not enforce its size limit')
            except OSError as exc:
                record('actual-bounded-tmpfs-enospc', exc.errno == errno.ENOSPC)
            # Capture is stubbed only to issue an actual write on the full filesystem.
            def capture(args, **kwargs):
                Path(args[-1]).write_bytes(b'capture fixture')
            with patch('luda.desktop.run', side_effect=capture):
                try:
                    d.observe()
                except DesktopError as exc:
                    record('full-filesystem-capture-diagnostic', exc.code == 'STORAGE_UNAVAILABLE' and exc.details['errno'] == 'ENOSPC' and not d.snapshots)
                else:
                    record('full-filesystem-capture-diagnostic', False)
            try:
                d.paste('fixture', 'staged payload')
            except DesktopError as exc:
                record('full-filesystem-paste-no-shortcut', exc.code == 'STORAGE_UNAVAILABLE' and not d.key.called)
            else:
                record('full-filesystem-paste-no-shortcut', False)
            record('failed-operation-tempfiles-cleaned', [p.name for p in root.iterdir()] == ['bounded-filler'])
            filler.unlink()
            subprocess.run(['mount', '-o', 'remount,ro', str(root)], check=True)
            try:
                d.observe()
            except DesktopError as exc:
                record('readonly-filesystem-capture-diagnostic', exc.code == 'STORAGE_UNAVAILABLE' and exc.details['errno'] == 'EROFS')
            else:
                record('readonly-filesystem-capture-diagnostic', False)
            with patch('luda.desktop.tempfile.gettempdir', return_value=str(root)):
                try:
                    Desktop()
                except DesktopError as exc:
                    record('readonly-filesystem-startup-diagnostic', exc.code == 'STORAGE_UNAVAILABLE' and exc.details['errno'] == 'EROFS')
                else:
                    record('readonly-filesystem-startup-diagnostic', False)
        finally:
            d.close()
            subprocess.run(['umount', str(root)], check=True)
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inside', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.inside:
        inside(args.inside)
    else:
        root = Path(__file__).resolve().parents[1]
        output = root / 'artifacts/storage'
        output.mkdir(parents=True, exist_ok=True)
        namespace = os.readlink('/proc/self/ns/mnt')
        result = subprocess.run(['unshare', '--user', '--map-root-user', '--mount', '--propagation', 'private',
                                 sys.executable, str(Path(__file__).resolve()), '--inside', namespace],
                                capture_output=True, text=True, timeout=30)
        (output / 'private-filesystem.log').write_text(result.stdout + result.stderr)
        print(result.stdout + result.stderr)
        if result.returncode:
            raise SystemExit(result.returncode)
        (output / 'results.json').write_text(result.stdout)
