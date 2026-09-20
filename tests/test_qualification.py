"""The evidence system must not promote incomplete or failing evidence."""
import importlib.util
import io
from pathlib import Path
import unittest
import tempfile

spec = importlib.util.spec_from_file_location('qualify', Path(__file__).resolve().parents[1] / 'scripts/qualify.py')
qualify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qualify)


class QualificationContracts(unittest.TestCase):
    catalog = {'features': [{'cases': [{'id': 'A-01', 'acceptance': 'Example'}]}]}

    def test_fingerprint_keeps_npm_lock_but_excludes_installed_dependencies(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);tool=root/'tests/tools/codex-cli';tool.mkdir(parents=True)
            lock=tool/'package-lock.json';lock.write_text('locked-v1')
            initial=qualify.source_fingerprint(root)
            binary=tool/'node_modules/@openai/codex/bin/codex';binary.parent.mkdir(parents=True);binary.write_bytes(b'installed-platform-binary')
            self.assertEqual(qualify.source_fingerprint(root),initial)
            binary.write_bytes(b'changed-platform-binary')
            self.assertEqual(qualify.source_fingerprint(root),initial)
            lock.write_text('locked-v2')
            self.assertNotEqual(qualify.source_fingerprint(root),initial)

    def test_fingerprint_includes_fixture_skill_and_plugin_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            cases=['requirements-browser.lock','tests/fixtures/browser.html','skills/luda/SKILL.md',
                   '.mcp.json','.codex-plugin/plugin.json','.github/workflows/tests.yml',
                   'integrations/silo/guest/agent-tools.py']
            prior=qualify.source_fingerprint(root)
            for name in cases:
                path=root/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('first')
                added=qualify.source_fingerprint(root)
                self.assertIn(name,added['files']);self.assertNotEqual(prior['sha256'],added['sha256'])
                path.write_text('changed')
                changed=qualify.source_fingerprint(root)
                self.assertNotEqual(added['sha256'],changed['sha256']);prior=changed
            cache=root/'src/luda/__pycache__/module.pyc';cache.parent.mkdir(parents=True);cache.write_bytes(b'cache')
            self.assertEqual(prior,qualify.source_fingerprint(root))

    def test_passing_tests_never_qualify_release(self):
        result = qualify.build_report(self.catalog, {'A-01': {'implementation': 'implemented', 'tests': ['test']}}, {'test': 'passed'})[0]
        self.assertEqual(result['test_status'], 'local_tests_passed')
        self.assertEqual(result['qualification'], 'unqualified')

    def test_missing_skipped_and_expected_failures_are_not_passes(self):
        for outcome in ['not_run', 'skipped', 'expected_failure']:
            with self.subTest(outcome=outcome):
                result = qualify.build_report(self.catalog, {'A-01': {'tests': ['test']}}, {'test': outcome})[0]
                self.assertEqual(result['test_status'], 'incomplete')

    def test_failure_dominates_partial_evidence(self):
        result = qualify.build_report(self.catalog, {'A-01': {'tests': ['a', 'b']}}, {'a': 'passed', 'b': 'failed'})[0]
        self.assertEqual(result['test_status'], 'failing')

    def test_absent_mapping_is_not_assessed(self):
        result = qualify.build_report(self.catalog, {}, {})[0]
        self.assertEqual(result['test_status'], 'no_evidence')
        self.assertEqual(result['implementation'], 'not_assessed')

    def test_unknown_requirement_fails(self):
        with self.assertRaises(ValueError):
            qualify.build_report(self.catalog, {'TYPO': {}}, {})

    def test_duplicate_test_reference_fails(self):
        with self.assertRaises(ValueError):
            qualify.build_report(self.catalog, {'A-01': {'tests': ['same', 'same']}}, {})

    def test_subtest_failure_is_not_silently_lost(self):
        class FailingSubtest(unittest.TestCase):
            def runTest(self):
                with self.subTest(value=1):
                    self.assertEqual(1, 2)
        test = FailingSubtest()
        result = unittest.TextTestRunner(stream=io.StringIO(), resultclass=qualify.EvidenceResult).run(unittest.TestSuite([test]))
        self.assertEqual(result.outcomes[test.id()], 'failed')


if __name__ == '__main__':
    unittest.main()
