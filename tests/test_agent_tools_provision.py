"""Private installer dependency integrity and failure cleanup contracts."""
import hashlib
import importlib.util
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('provision_agent_tools', Path(__file__).resolve().parents[1] / 'scripts/provision_agent_tools.py')
provisioner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(provisioner)


class ProvisionTools(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def test_download_verifies_bytes_before_use(self):
        payload = b'owned fixture archive'
        with patch.object(provisioner, 'urlopen', return_value=io.BytesIO(payload)) as request:
            provisioner.download('https://nodejs.org/fixture', self.root / 'archive', hashlib.sha256(payload).hexdigest())
        self.assertEqual((self.root / 'archive').read_bytes(), payload)
        request.assert_called_once_with('https://nodejs.org/fixture', timeout=30)

    def test_corrupt_download_refuses_execution_and_cleans_payload(self):
        with patch.object(provisioner, 'urlopen', return_value=io.BytesIO(b'corrupt')), patch.object(provisioner.subprocess, 'run') as run:
            with self.assertRaisesRegex(ValueError, 'integrity'):
                provisioner.provision(self.root, self.root)
        run.assert_not_called()
        self.assertEqual(list(self.root.iterdir()), [])

    def test_failed_download_cleans_payload(self):
        with patch.object(provisioner, 'urlopen', side_effect=TimeoutError('network timeout')):
            with self.assertRaises(TimeoutError):
                provisioner.provision(self.root, self.root)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_unsupported_architecture_does_not_download(self):
        with patch.object(provisioner.platform, 'machine', return_value='riscv64'), patch.object(provisioner, 'download') as download:
            with self.assertRaisesRegex(ValueError, 'arm64 or x64'):
                provisioner.provision(self.root, self.root)
        download.assert_not_called()
        self.assertEqual(list(self.root.iterdir()), [])

    def test_existing_directory_is_not_replaced(self):
        existing = self.root / 'agent-tools'; existing.mkdir()
        note = existing / 'user-file'; note.write_text('preserve')
        with self.assertRaises(FileExistsError):
            provisioner.provision(self.root, self.root)
        self.assertEqual(note.read_text(), 'preserve')

    def test_package_failure_cleans_payload_and_isolates_npm(self):
        source = self.root / 'source'; source.mkdir()
        for name in ('package.json', 'package-lock.json'):
            (source / name).write_text('{}')
        release = self.root / 'release'; release.mkdir()
        def unpack(scratch, **kwargs):
            architecture = {'aarch64':'arm64','x86_64':'x64'}[provisioner.platform.machine()]
            (scratch / f'node-v{provisioner.NODE_VERSION}-linux-{architecture}').mkdir()
        with patch.object(provisioner, 'download'), patch.object(provisioner.tarfile, 'open') as archive, patch.object(provisioner.subprocess, 'run', side_effect=subprocess.TimeoutExpired('npm', 180)) as run:
            archive.return_value.__enter__.return_value.extractall.side_effect = unpack
            with self.assertRaises(subprocess.TimeoutExpired):
                provisioner.provision(release, source)
        command = run.call_args.args[0]
        self.assertIn('--ignore-scripts', command)
        self.assertEqual(command[2], 'ci')
        environment = run.call_args.kwargs['env']
        self.assertTrue(environment['HOME'].startswith(str(release)))
        self.assertNotIn('NODE_OPTIONS', environment)
        self.assertEqual(list(release.iterdir()), [])
