"""The evidence system must not promote incomplete or failing evidence."""
import importlib.util
import io
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('qualify', Path(__file__).resolve().parents[1] / 'scripts/qualify.py')
qualify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(qualify)


class QualificationContracts(unittest.TestCase):
    catalog = {'features': [{'cases': [{'id': 'A-01', 'acceptance': 'Example'}]}]}

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
