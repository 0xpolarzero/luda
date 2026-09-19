#!/usr/bin/env python3
"""Produce requirement-linked evidence. A passing test never grants qualification."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


class EvidenceResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.outcomes = {}

    def addSuccess(self, test):
        super().addSuccess(test)
        self.outcomes.setdefault(test.id(), 'passed')

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self.outcomes[test.id()] = 'failed'

    def addError(self, test, err):
        super().addError(test, err)
        self.outcomes[test.id()] = 'error'

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self.outcomes[test.id()] = 'skipped'

    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err)
        self.outcomes[test.id()] = 'expected_failure'

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        self.outcomes[test.id()] = 'unexpected_success'

    def addSubTest(self, test, subtest, err):
        super().addSubTest(test, subtest, err)
        if err is not None:
            self.outcomes[test.id()] = 'failed'


def source_fingerprint(root):
    """Hash actual sources, including uncommitted changes, rather than just HEAD."""
    paths = [p for folder in ('src', 'tests', 'scripts', 'docs')
             for p in (root / folder).rglob('*')
             if p.is_file() and '__pycache__' not in p.parts and p.suffix in ('.py', '.json', '.md')]
    paths += [root / 'pyproject.toml', root / 'requirements.lock']
    files = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted(paths) if p.exists()}
    digest = hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest()
    return {'sha256': digest, 'files': files}


def build_report(catalog, mapping, outcomes):
    cases = {case['id']: case for feature in catalog['features'] for case in feature['cases']}
    if len(cases) != sum(len(f['cases']) for f in catalog['features']):
        raise ValueError('Duplicate requirement IDs')
    unknown = set(mapping) - set(cases)
    if unknown:
        raise ValueError(f'Unknown requirements: {sorted(unknown)}')
    report = []
    for case_id, case in cases.items():
        entry = mapping.get(case_id, {})
        implementation = entry.get('implementation', 'not_assessed')
        if implementation not in ('not_assessed', 'missing', 'partial', 'implemented'):
            raise ValueError(f'Invalid implementation status for {case_id}')
        tests = entry.get('tests', [])
        if len(tests) != len(set(tests)):
            raise ValueError(f'Duplicate test references for {case_id}')
        evidence = [{'test': name, 'outcome': outcomes.get(name, 'not_run')} for name in tests]
        states = {e['outcome'] for e in evidence}
        tested = 'no_evidence'
        if states & {'failed', 'error', 'unexpected_success'}:
            tested = 'failing'
        elif states == {'passed'}:
            tested = 'local_tests_passed'
        elif states:
            tested = 'incomplete'
        report.append({'id': case_id, 'acceptance': case['acceptance'],
                       'implementation': implementation, 'test_status': tested,
                       'qualification': 'unqualified', 'evidence': evidence,
                       'limits': entry.get('limits', 'No evidence mapped; absence is not proof of missing implementation.')})
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'artifacts/qualification/unit.json')
    parser.add_argument('--pattern', default='test_*.py')
    args = parser.parse_args()
    suite = unittest.defaultTestLoader.discover(str(ROOT / 'tests'), pattern=args.pattern)
    result = unittest.TextTestRunner(verbosity=2, resultclass=EvidenceResult).run(suite)
    catalog = json.loads((ROOT / 'docs/requirements.json').read_text())
    mapping = json.loads((ROOT / 'docs/test-map.json').read_text())['requirements']
    cases = build_report(catalog, mapping, result.outcomes)
    revision = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True, capture_output=True).stdout.strip()
    report = {'schema_version': 1, 'created_at': datetime.now(timezone.utc).isoformat(),
              'revision': revision, 'source': source_fingerprint(ROOT),
              'environment': {'system': platform.system(), 'release': platform.release(),
                              'architecture': platform.machine(), 'python': platform.python_version()},
              'suite': 'unit', 'outcomes': result.outcomes, 'requirements': cases,
              'summary': dict(Counter(c['test_status'] for c in cases)),
              'policy': 'Local tests are evidence for named assertions only. No case is automatically release-qualified.'}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')
    print(f'Evidence: {args.output}')
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    sys.exit(main())
