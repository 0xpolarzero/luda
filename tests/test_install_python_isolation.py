"""Installed-wheel provenance under polluted Python startup settings."""
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
import zipfile
import test_installation as fixture

installer = fixture.installer


class InstallerPythonIsolation(unittest.TestCase):
    setUp = fixture.Installation.setUp

    def wheel(self, destination):
        destination.mkdir()
        wheel = destination / 'luda-1.0.0-py3-none-any.whl'
        files = {'luda/__init__.py': '', 'luda/server.py': 'INSTALLED = True\n',
                 'luda-1.0.0.dist-info/METADATA': 'Metadata-Version: 2.1\nName: luda\nVersion: 1.0.0\n',
                 'luda-1.0.0.dist-info/WHEEL': 'Wheel-Version: 1.0\nGenerator: luda-test\nRoot-Is-Purelib: true\nTag: py3-none-any\n'}
        files['luda-1.0.0.dist-info/RECORD'] = ''.join(name + ',,\n' for name in files) + 'luda-1.0.0.dist-info/RECORD,,\n'
        with zipfile.ZipFile(wheel, 'w') as archive:
            for name, content in files.items(): archive.writestr(name, content)
        return wheel

    def test_actual_install_ignores_checkout_metadata_and_python_home(self):
        package = self.source / 'src/luda'; package.mkdir()
        (package / '__init__.py').write_text('')
        (package / 'server.py').write_text('INSTALLED = False\n')
        metadata = self.source / 'src/luda.egg-info'; metadata.mkdir()
        (metadata / 'PKG-INFO').write_text('Metadata-Version: 2.1\nName: luda\nVersion: 1.0.0\n')
        wheel = self.wheel(self.root / 'baseline-wheel')
        baseline = self.root / 'baseline-venv'
        subprocess.run([sys.executable, '-I', '-m', 'venv', str(baseline)], check=True, capture_output=True, timeout=30)
        environment = {key: value for key, value in os.environ.items() if not key.startswith('PYTHON')}
        environment['PYTHONPATH'] = str(self.source / 'src')
        # Original direct pip command sees source egg-info and skips the wheel.
        old = subprocess.run([str(baseline / 'bin/python'), '-m', 'pip', '--isolated', 'install', '--no-deps', str(wheel)], env=environment, capture_output=True, timeout=30)
        self.assertEqual(old.returncode, 0, old.stderr)
        missing = subprocess.run([str(baseline / 'bin/python'), '-I', '-c', 'import luda'], capture_output=True, timeout=5)
        self.assertNotEqual(missing.returncode, 0, 'Baseline must reproduce missing installed package')
        commands = []
        def runner(command):
            args = list(map(str, command)); commands.append(args)
            self.assertEqual(args[1], '-I')
            if 'pip' in args: self.assertIn('--isolated', args)
            if any(part.endswith('provision_agent_tools.py') for part in args):
                return  # External installer payload is covered separately.
            if '--require-hashes' in args:
                return  # Synthetic no-dependency wheel; no network or production package install.
            if 'wheel' in args:
                self.wheel(Path(args[args.index('--wheel-dir') + 1])); return
            installer.invoke(args, timeout=30)
        with patch.dict(os.environ, {'PYTHONPATH': str(self.source / 'src'), 'PYTHONHOME': '/missing-test-python-home', 'PYTHONUSERBASE': str(self.root / 'wrong-user-base')}):
            installed = installer.install(self.prefix, self.source, runner)
        python = self.prefix / 'current/.venv/bin/python'
        result = subprocess.check_output([str(python), '-I', '-c', 'import json,luda.server;print(json.dumps([luda.server.INSTALLED,luda.server.__file__]))'], text=True, timeout=5)
        value, path = json.loads(result)
        self.assertTrue(value)
        self.assertTrue(Path(path).resolve().is_relative_to((self.prefix / 'current').resolve()))
        self.assertEqual(installed['status'], 'installed')
        self.assertEqual((package / 'server.py').read_text(), 'INSTALLED = False\n')

    def test_python_startup_variables_do_not_reach_backend_children(self):
        output = self.root / 'child.json'
        child = 'import json,os,sys;open(sys.argv[1],"w").write(json.dumps(sorted(k for k in os.environ if k.startswith("PYTHON"))))'
        parent = 'import subprocess,sys;subprocess.run([sys.executable,"-c",sys.argv[1],sys.argv[2]],check=True)'
        with patch.dict(os.environ, {'PYTHONPATH': '/synthetic-path', 'PYTHONHOME': '/synthetic-home', 'PYTHONINSPECT': '1'}):
            installer.invoke([sys.executable, '-I', '-c', parent, child, str(output)], timeout=5)
        self.assertEqual(json.loads(output.read_text()), [])
