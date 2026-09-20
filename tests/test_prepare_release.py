"""Committed artifact identity is independent of the checkout and Git attributes."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import prepare_release as release


class PrepareReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(); self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name); self.repo = self.root / 'repo'; self.repo.mkdir()
        self.git('init', '-q'); self.git('config', 'user.name', 'Fixture'); self.git('config', 'user.email', 'fixture@example.invalid')
        for name in release.REQUIRED:
            path = self.repo / name; path.parent.mkdir(parents=True, exist_ok=True); path.write_text('committed fixture\n')
        (self.repo / 'scripts/install.sh').chmod(0o755)
        self.commit()

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.repo), *args], stderr=subprocess.PIPE).decode().strip()

    def commit(self):
        self.git('add', '.'); self.git('commit', '-qm', 'fixture')
        self.sha = self.git('rev-parse', 'HEAD')

    def prepare(self, name='out', **kwargs):
        return release.prepare(self.repo, kwargs.get('commit', self.sha),
            kwargs.get('url', 'https://example.invalid/releases/luda-' + self.sha + '.tar.gz'), self.root / name)

    def test_exact_reproducible_archive_survives_dirty_checkout_and_guest_extraction(self):
        first = self.prepare()
        (self.repo / 'src/luda/server.py').write_text('UNCOMMITTED_DO_NOT_SHIP')
        (self.repo / 'untracked-secret').write_text('UNTRACKED_DO_NOT_SHIP')
        second = self.prepare('second')
        self.assertEqual(first, second)
        for path in (self.root / 'out').iterdir():
            self.assertEqual(path.read_bytes(), (self.root / 'second' / path.name).read_bytes())
        archive = self.root / 'out' / first['archive']
        self.assertEqual(hashlib.sha256(archive.read_bytes()).hexdigest(), first['sha256'])
        spec = importlib.util.spec_from_file_location('release_guest_fixture', ROOT / 'integrations/silo/guest/agent-tools.py')
        guest = importlib.util.module_from_spec(spec); spec.loader.exec_module(guest)
        manifest = guest.manifest(self.root / 'out/agent-tools-release.json')
        self.assertEqual(manifest['source_commit'], self.sha)
        extracted = guest.extract(archive, self.root / 'extracted', self.sha)
        self.assertEqual((extracted / 'src/luda/server.py').read_text(), 'committed fixture\n')
        self.assertFalse((extracted / 'untracked-secret').exists())
        self.assertEqual((extracted / 'scripts/install.sh').stat().st_mode & 0o777, 0o755)

    def test_source_attributes_cannot_silently_omit_or_rewrite_committed_files(self):
        for attribute in ('src/luda/server.py export-ignore\n', 'src/luda/server.py export-subst\n'):
            with self.subTest(attribute=attribute):
                (self.repo / '.gitattributes').write_text(attribute)
                (self.repo / 'src/luda/server.py').write_text('$Format:%H$\n'); self.commit()
                with self.assertRaises(ValueError): self.prepare()
                self.assertFalse((self.root / 'out').exists())

    def test_links_are_refused_and_existing_output_is_preserved(self):
        self.prepare(); before = (self.root / 'out/provenance.json').read_bytes()
        with self.assertRaises(FileExistsError): self.prepare()
        self.assertEqual((self.root / 'out/provenance.json').read_bytes(), before)
        (self.repo / 'link').symlink_to('requirements.lock'); self.commit()
        with self.assertRaises(ValueError): self.prepare('linked')
        self.assertFalse((self.root / 'linked').exists())

    def test_replace_refs_cannot_change_the_committed_source(self):
        original = self.sha
        (self.repo / 'src/luda/server.py').write_text('replacement contents'); self.commit()
        self.git('replace', original, self.sha)
        proof = self.prepare(commit=original, url='https://example.invalid/luda-' + original + '.tar.gz')
        import tarfile
        with tarfile.open(self.root / 'out' / proof['archive']) as archive:
            self.assertEqual(archive.extractfile('luda-' + original + '/src/luda/server.py').read(), b'committed fixture\n')
        self.assertEqual(proof['commit'], original)

    def test_concurrent_empty_directory_is_not_replaced(self):
        original = release.publish; identities = []
        def race(stage, output):
            output.mkdir(); identities.append(output.stat().st_ino)
            original(stage, output)
        with patch.object(release, 'publish', side_effect=race), self.assertRaises(FileExistsError):
            self.prepare()
        self.assertEqual((self.root / 'out').stat().st_ino, identities[0])
        self.assertEqual(list((self.root / 'out').iterdir()), [])

    def test_moving_refs_and_noncommit_objects_are_refused(self):
        for commit in ('HEAD', self.sha[:8], self.git('rev-parse', 'HEAD^{tree}')):
            with self.subTest(commit=commit), self.assertRaises(ValueError): self.prepare(commit=commit)
        self.assertFalse((self.root / 'out').exists())

    def test_unsafe_or_mismatched_urls_leave_no_output(self):
        suffix = '/luda-' + self.sha + '.tar.gz'
        for url in ('http://example.invalid' + suffix, 'https://user:pass@example.invalid' + suffix,
                    'https://example.invalid' + suffix + '?token=private', 'https://example.invalid' + suffix + '#fragment',
                    'https://example.invalid/wrong.tar.gz', 'https://example.invalid/\n' + suffix):
            with self.subTest(url=url), self.assertRaises(ValueError): self.prepare(url=url)
        self.assertFalse((self.root / 'out').exists())


if __name__ == '__main__':
    unittest.main()
