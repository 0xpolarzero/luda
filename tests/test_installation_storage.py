"""Installer write failure must preserve current and permit a clean retry."""
import errno
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('installation_fixture', Path(__file__).with_name('test_installation.py'))
fixture = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fixture)
installer = fixture.installer


class InstallationStorage(unittest.TestCase):
    def test_owner_marker_failure_cleans_only_new_release(self):
        setup = fixture.Installation()
        setup.setUp()
        self.addCleanup(setup.doCleanups)
        first = installer.install(setup.prefix, setup.source, setup.runner)
        (setup.source / 'src/file.py').write_text('new release')
        real_atomic = installer.atomic_json
        def fail_owner(path, value):
            if path.name == '.luda-release-owner.json':
                raise OSError(errno.ENOSPC, 'injected marker write failure')
            return real_atomic(path, value)
        with patch.object(installer, 'atomic_json', side_effect=fail_owner):
            with self.assertRaises(OSError):
                installer.install(setup.prefix, setup.source, setup.runner)
        self.assertEqual((setup.prefix / 'current').readlink().name, first['release'])
        self.assertEqual([p.name for p in (setup.prefix / 'releases').iterdir()], [first['release']])
        second = installer.install(setup.prefix, setup.source, setup.runner)
        self.assertNotEqual(second['release'], first['release'])

    def test_atomic_metadata_write_failure_preserves_previous_bytes(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'marker.json'
            path.write_bytes(b'previous committed bytes')
            with patch.object(installer.os, 'fsync', side_effect=OSError(errno.ENOSPC, 'injected fsync failure')):
                with self.assertRaises(OSError):
                    installer.atomic_json(path, {'new': 'metadata'})
            self.assertEqual(path.read_bytes(), b'previous committed bytes')
            self.assertEqual([p.name for p in Path(directory).iterdir()], ['marker.json'])


if __name__ == '__main__':
    unittest.main()
