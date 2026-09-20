"""Verify the checked-in offline browser fixture's dependency identity."""
import hashlib
import json
from pathlib import Path
import unittest

FIXTURE = Path(__file__).parent / 'fixtures/rich-editor'


class RichEditorAssets(unittest.TestCase):
    def test_bundled_sources_match_recorded_hashes(self):
        identity = json.loads((FIXTURE / 'bundle-identity.json').read_text())
        for name, digest in identity['files'].items():
            with self.subTest(file=name):
                self.assertEqual(hashlib.sha256((FIXTURE / name).read_bytes()).hexdigest(), digest)

    def test_runtime_versions_and_notices_match_lock(self):
        identity = json.loads((FIXTURE / 'bundle-identity.json').read_text())
        lock = json.loads((FIXTURE / 'package-lock.json').read_text())
        notices = (FIXTURE / 'THIRD_PARTY_NOTICES.md').read_text()
        for name, version in identity['packages'].items():
            with self.subTest(package=name):
                self.assertEqual(lock['packages']['node_modules/' + name]['version'], version)
                self.assertIn(name, notices)
        declared = json.loads((FIXTURE / 'package.json').read_text())['dependencies']
        for name, version in declared.items():
            self.assertEqual(identity['packages'][name], version)


if __name__ == '__main__':
    unittest.main()
