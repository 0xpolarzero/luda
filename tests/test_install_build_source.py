"""Build input isolation, source preservation, and actual setuptools regression."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import unittest
import zipfile
import test_installation as fixture

installer = fixture.installer


class BuildSource(unittest.TestCase):
    setUp = fixture.Installation.setUp
    runner = fixture.Installation.runner

    def test_staging_ignores_stale_build_and_preserves_source(self):
        stale = self.source / 'build/lib/luda/_input_guard.py'
        stale.parent.mkdir(parents=True)
        stale.write_text('stale module')
        metadata = self.source / 'src/luda.egg-info/SOURCES.txt'
        metadata.parent.mkdir()
        metadata.write_text('stale metadata')
        (self.source / 'uv.lock').write_text('packaged lock')
        initial = installer.release_identity(self.source)
        (self.source / 'uv.lock').write_text('changed lock')
        self.assertNotEqual(initial, installer.release_identity(self.source))
        self.source.chmod(0o555)
        stages = []
        def run(command):
            if 'wheel' in list(map(str, command)):
                stage = Path(command[-1]); stages.append(stage)
                self.assertNotEqual(stage, self.source)
                self.assertFalse((stage / 'build').exists())
                self.assertFalse((stage / 'src/luda.egg-info').exists())
                self.assertEqual((stage / 'uv.lock').read_text(), 'changed lock')
                self.assertEqual(installer.release_identity(stage), installer.release_identity(self.source))
            self.runner(command)
        installer.install(self.prefix, self.source, run)
        self.assertTrue(stages)
        self.assertTrue(all(not stage.exists() for stage in stages))
        files = json.loads((self.prefix / 'current/release.json').read_text())['files']
        self.assertFalse(any(name.startswith('.build-source-') for name in files))
        self.assertEqual(stale.read_text(), 'stale module')
        self.assertEqual(metadata.read_text(), 'stale metadata')
        self.assertEqual(self.source.stat().st_mode & 0o777, 0o555)
        self.source.chmod(0o755)

    def test_failed_build_removes_stage_and_preserves_selection(self):
        previous = installer.install(self.prefix, self.source, self.runner)
        (self.source / 'src/file.py').write_text('upgrade')
        stages = []
        def fail(command):
            if 'wheel' in list(map(str, command)):
                stages.append(Path(command[-1]))
                raise installer.InstallError('build failed')
            self.runner(command)
        with self.assertRaises(installer.InstallError):
            installer.install(self.prefix, self.source, fail)
        self.assertTrue(stages)
        self.assertTrue(all(not stage.exists() for stage in stages))
        self.assertEqual((self.prefix / 'current').resolve().name, previous['release'])

    @unittest.skipUnless(importlib.util.find_spec('setuptools') and importlib.util.find_spec('wheel'), 'Install build-requirements.lock for actual wheel regression')
    def test_actual_wheel_excludes_stale_module(self):
        (self.source / 'pyproject.toml').write_text('[build-system]\nrequires=["setuptools>=68"]\nbuild-backend="setuptools.build_meta"\n[project]\nname="luda"\nversion="1.0.0"\n[tool.setuptools.packages.find]\nwhere=["src"]\n')
        (self.source / 'MANIFEST.in').write_text('include uv.lock\n')
        (self.source / 'uv.lock').write_text('owned fixture lock')
        package = self.source / 'src/luda'; package.mkdir()
        (package / '__init__.py').write_text('')
        (package / 'current.py').write_text('CURRENT = True\n')
        stale = self.source / 'build/lib/luda/_input_guard.py'
        stale.parent.mkdir(parents=True); stale.write_text('STALE = True\n')
        def build(directory, name):
            output = self.root / name; output.mkdir()
            result = subprocess.run([sys.executable, '-c', 'import setuptools.build_meta,sys;setuptools.build_meta.build_wheel(sys.argv[1])', str(output)], cwd=directory, capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode(errors='replace'))
            with zipfile.ZipFile(next(output.glob('*.whl'))) as wheel:
                return {name for name in wheel.namelist() if name.startswith('luda/')}
        # Independent baseline reproduces setuptools reuse of stale build/lib.
        self.assertIn('luda/_input_guard.py', build(self.source, 'baseline'))
        identity = installer.release_identity(self.source)
        with installer.build_source(self.source, self.root, identity) as stage:
            actual = build(stage, 'isolated')
        self.assertEqual(actual, {'luda/__init__.py', 'luda/current.py'})
        self.assertEqual(stale.read_text(), 'STALE = True\n')
