import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'integrations/silo'
spec = importlib.util.spec_from_file_location('silo_tools', ASSETS / 'guest/agent-tools.py')
tools = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tools)
COMMIT = '1' * 40
RELEASE = {'schema_version': 1, 'enabled': True, 'source_commit': COMMIT,
           'source_sha256': '2' * 64, 'source_url': 'https://example.invalid/luda.tar.gz'}
REQUIRED = ('pyproject.toml', 'MANIFEST.in', 'requirements.lock', 'build-requirements.lock',
            'scripts/bootstrap_guest.py', 'scripts/manage_install.py', 'scripts/install.sh',
            'src/luda/server.py', 'skills/luda/SKILL.md')


def archive(path, extra=None, missing=None):
    with tarfile.open(path, 'w:gz') as output:
        for name in REQUIRED:
            if name == missing:
                continue
            value = b'fixture'
            info = tarfile.TarInfo('luda-' + COMMIT + '/' + name)
            info.size = len(value)
            output.addfile(info, io.BytesIO(value))
        if extra:
            output.addfile(extra, io.BytesIO(b'x' * extra.size))


class SiloIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name)
        self.fetch = lambda release, path: archive(path)
        self.install = Mock(return_value={'ok': True, 'installation_completed': True,
                                         'configuration_generated': True, 'tools': {'ready': True},
                                         'selected_release': '0.1.0-' + 'a' * 16})

    def ensure(self, release=None, **kwargs):
        return tools.ensure(release or RELEASE, self.state, fetch=self.fetch,
                            install=self.install, running=lambda: True, **kwargs)

    def test_manifest_disabled_by_default_and_strictly_validated(self):
        self.assertFalse(tools.manifest(ASSETS / 'guest/agent-tools-release.json')['enabled'])
        candidates = [dict(RELEASE, source_commit='main'), dict(RELEASE, source_sha256='bad'),
                      dict(RELEASE, source_url='http://example.invalid/file'),
                      dict(RELEASE, source_url='https://secret@example.invalid/file'),
                      dict(RELEASE, source_url='https://example.invalid/file?token=secret'),
                      dict(RELEASE, unknown='secret'), {'schema_version': 1, 'enabled': 1}]
        path = self.state / 'manifest.json'
        for value in candidates:
            path.write_text(json.dumps(value))
            with self.subTest(value=value), self.assertRaises(tools.OnboardingError):
                tools.manifest(path)
        path.write_text(json.dumps(RELEASE))
        self.assertEqual(tools.manifest(path), RELEASE)

    def test_disabled_does_not_probe_desktop_or_install(self):
        running = Mock(side_effect=AssertionError('must not probe'))
        result = tools.ensure({'enabled': False}, self.state, running=running, install=self.install)
        self.assertEqual(result['state'], 'unconfigured')
        self.install.assert_not_called()
        self.assertFalse((self.state / 'status.json').exists())

    def test_stopped_defers_and_later_running_installs_once(self):
        result = tools.ensure(RELEASE, self.state, running=lambda: False, install=self.install)
        self.assertEqual(result['state'], 'pending')
        self.install.assert_not_called()
        result = self.ensure()
        self.assertEqual(result['state'], 'ready')
        self.ensure()
        self.install.assert_called_once()
        self.assertNotIn('source_url', result)

    def test_install_observes_durable_uncertain_marker_and_fresh_output(self):
        original = self.install.return_value
        def inspect(source, output):
            state = tools.read_json(self.state / 'status.json')
            self.assertEqual(state['state'], 'unconfirmed')
            self.assertIsNone(state['installation_completed'])
            self.assertFalse(output.exists())
            self.assertTrue((source / 'requirements.lock').exists())
            return original
        self.install.side_effect = inspect
        self.assertEqual(self.ensure()['state'], 'ready')

    def test_failed_and_interrupted_attempts_never_auto_retry(self):
        self.install.side_effect = RuntimeError('sensitive diagnostic')
        result = self.ensure()
        self.assertEqual(result['state'], 'unconfirmed')
        self.assertIsNone(result['installation_completed'])
        self.assertNotIn('sensitive', json.dumps(result))
        self.ensure()
        self.install.assert_called_once()
        self.assertFalse(result['automatic_retry_allowed'])
        self.ensure(reviewed=True)
        self.assertEqual(self.install.call_count, 2)

    def test_external_interruption_preserves_marker(self):
        self.install.side_effect = KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            self.ensure()
        self.install.side_effect = None
        result = self.ensure()
        self.assertEqual(result['state'], 'unconfirmed')
        self.install.assert_called_once()

    def test_installed_not_ready_remains_installed_and_no_automatic_update(self):
        self.install.return_value.update(ok=False, configuration_generated=False, tools={'ready': False})
        result = self.ensure()
        self.assertEqual(result['state'], 'attention')
        self.assertTrue(result['installation_completed'])
        self.assertFalse(result['last_ready'])
        self.ensure(dict(RELEASE, source_sha256='3' * 64))
        self.install.assert_called_once()

    def test_new_manifest_reports_update_without_install(self):
        self.ensure()
        result = self.ensure(dict(RELEASE, source_sha256='3' * 64))
        self.assertEqual(result['state'], 'update_available')
        self.install.assert_called_once()

    def test_download_checksum_and_https_redirect(self):
        data = b'archive bytes'
        response = io.BytesIO(data)
        response.geturl = lambda: RELEASE['source_url']
        opener = Mock()
        opener.open.return_value = response
        with patch.object(tools.urllib.request, 'build_opener', return_value=opener):
            with self.assertRaises(tools.OnboardingError):
                tools.download(RELEASE, self.state / 'wrong.tar.gz')
        with self.assertRaises(tools.OnboardingError):
            tools.HttpsRedirect().redirect_request(None, None, 302, '', {}, 'http://example.invalid/no')
        response = io.BytesIO(data)
        response.geturl = lambda: RELEASE['source_url']
        opener.open.return_value = response
        with patch.object(tools.urllib.request, 'build_opener', return_value=opener):
            tools.download(dict(RELEASE, source_sha256=hashlib.sha256(data).hexdigest()), self.state / 'valid.tar.gz')

    def test_archive_rejects_traversal_links_duplicates_and_missing_locks(self):
        cases = []
        traversal = tarfile.TarInfo('luda-' + COMMIT + '/../escape');cases.append(traversal)
        link = tarfile.TarInfo('luda-' + COMMIT + '/link');link.type = tarfile.SYMTYPE;link.linkname = '/etc';cases.append(link)
        hardlink = tarfile.TarInfo('luda-' + COMMIT + '/hardlink');hardlink.type = tarfile.LNKTYPE;hardlink.linkname = 'pyproject.toml';cases.append(hardlink)
        cases.append(tarfile.TarInfo('luda-' + COMMIT + '/pyproject.toml'))
        for index, member in enumerate(cases):
            path = self.state / f'bad-{index}.tar.gz';archive(path, extra=member)
            with self.subTest(index=index), self.assertRaises((tools.OnboardingError, FileExistsError)):
                tools.extract(path, self.state / f'extract-{index}', COMMIT)
        path = self.state / 'missing.tar.gz';archive(path, missing='requirements.lock')
        with self.assertRaises(tools.OnboardingError):
            tools.extract(path, self.state / 'missing', COMMIT)
        self.assertFalse((self.state / 'escape').exists())

    def test_projection_excludes_untrusted_text_paths_and_fake_booleans(self):
        value = tools.project({'state': 'secret', 'installation_completed': 'true', 'last_ready': 1,
                               'source_url': 'secret', 'selected_release': '/private/secret',
                               'checked_at': 'secret', 'error': 'secret', 'password': 'secret'})
        self.assertEqual(value['state'], 'unconfirmed')
        self.assertIsNone(value['installation_completed'])
        self.assertIsNone(value['last_ready'])
        self.assertNotIn('secret', json.dumps(value))

    def test_desktop_probe_only_uses_status_and_never_starts(self):
        def run(argv, **kwargs):
            self.assertEqual(argv, ['/usr/local/bin/silo-desktop', 'status'])
            kwargs['stdout'].write(json.dumps({'version': '1', 'installed': True,
                                             'user': 'silo-desktop', 'state': 'stopped', 'password': 'secret'}).encode())
            return subprocess.CompletedProcess(argv, 0)
        with patch.object(tools.subprocess, 'run', side_effect=run):
            self.assertFalse(tools.desktop_running())

    def test_guest_patch_applies_and_matches_canonical_assets(self):
        checkout = self.state / 'checkout';checkout.mkdir()
        subprocess.run(['git', 'init', '-q', str(checkout)], check=True)
        subprocess.run(['git', '-C', str(checkout), 'apply', str(ASSETS / '0001-guest-onboarding.patch')], check=True)
        for name in ('agent-tools.py', 'agent-tools-release.json'):
            self.assertEqual((checkout / 'app/SiloUI/src-tauri/guest' / name).read_bytes(),
                             (ASSETS / 'guest' / name).read_bytes())
