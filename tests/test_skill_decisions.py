"""Runner contract tests use a fake CLI, never a model or live desktop."""
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/evaluation/skill_decisions.py'
spec = importlib.util.spec_from_file_location('skill_decisions', SCRIPT)
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class DecisionsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.skill = self.base / 'skill'
        (self.skill / 'references').mkdir(parents=True)
        (self.skill / 'SKILL.md').write_text('PUBLIC SKILL\n')
        for name in runner.REFERENCE_NAMES:
            (self.skill / 'references' / name).write_text(f'PUBLIC REFERENCE {name}\n')
        self.case = {'id': 'case-01', 'public_prompt': 'Exact public prompt.\nÉvidence.'}
        self.cli = self.base / 'codex'

    def fake(self, body):
        self.cli.write_text('#!/usr/bin/env python3\n' + body)
        self.cli.chmod(0o700)

    def run_case(self, timeout=5):
        return runner.run_case(self.case, self.skill, self.base / 'out', str(self.cli), timeout, self.base / 'auth')

    def test_isolated_context_exact_prompt_and_ungraded_success(self):
        self.fake('''import os, sys, json
from pathlib import Path
args = sys.argv
assert args[args.index('--model')+1] == 'gpt-5.6-sol'
assert not any('reasoning_effort' in a for a in args)
workspace = Path(args[args.index('-C')+1])
assert sorted(p.name for p in workspace.iterdir()) == ['luda']
assert len(list(workspace.rglob('*.md'))) == 8
assert not (Path(os.environ['CODEX_HOME']) / 'config.toml').exists()
assert 'PUBLIC SKILL' in next(a for a in args if a.startswith('developer_instructions='))
assert sys.stdin.read() == 'Exact public prompt.\\nÉvidence.'
Path(args[args.index('--output-last-message')+1]).write_text('Needs a semantic evaluator.')
print(json.dumps({'type':'thread.started','thread_id':'fresh-id'}))
print(json.dumps({'type':'turn.completed'}))
''')
        result = self.run_case()
        self.assertEqual(result['status'], 'recorded')
        self.assertEqual(result['semantic_grade'], 'ungraded')
        self.assertEqual(result['thread_ids'], ['fresh-id'])
        self.assertEqual((self.base / 'out/prompt.txt').read_text(), self.case['public_prompt'])
        self.assertIn('final.txt', result['artifact_hashes'])
        self.assertFalse(Path(result['argv'][result['argv'].index('-C') + 1]).exists())
        with self.assertRaises(FileExistsError):
            self.run_case()

    def test_timeout_preserves_partial_events(self):
        self.fake("import time\nprint('{\"type\":\"thread.started\",\"thread_id\":\"partial\"}', flush=True)\ntime.sleep(60)\n")
        result = self.run_case(timeout=.1)
        self.assertEqual(result['status'], 'timeout')
        self.assertEqual(result['thread_ids'], ['partial'])
        self.assertTrue(result['timeout'])

    def test_cli_failure_is_unassessable(self):
        self.fake("import sys\nprint('Authentication unavailable', file=sys.stderr)\nsys.exit(2)\n")
        result = self.run_case()
        self.assertEqual(result['status'], 'unassessable')
        self.assertEqual(result['returncode'], 2)
        self.assertEqual(result['semantic_grade'], 'ungraded')

    def test_tool_use_cannot_count_as_recorded_decision(self):
        self.fake('''import sys,json
from pathlib import Path
Path(sys.argv[sys.argv.index('--output-last-message')+1]).write_text('Done')
for e in [{'type':'thread.started','thread_id':'id'}, {'type':'item.completed','item':{'type':'command_execution','command':'ls'}}, {'type':'turn.completed'}]: print(json.dumps(e))
''')
        self.assertEqual(self.run_case()['status'], 'unassessable')

    def test_missing_cli_preserves_failure(self):
        result = self.run_case()
        self.assertEqual(result['status'], 'unassessable')
        self.assertIn('launch_error', result)

    def test_public_loader_rejects_private_criteria_and_duplicate_ids(self):
        path = self.base / 'cases.json'
        for cases in ([dict(self.case, required_semantics=['PRIVATE'])], [self.case, self.case]):
            path.write_text(json.dumps({'schema_version': 1, 'cases': cases}))
            with self.assertRaises(ValueError):
                runner.load_cases(path)
        path.write_text(json.dumps({'schema_version': 1, 'cases': [self.case]}))
        self.assertEqual(runner.load_cases(path), [self.case])
        path.write_text(json.dumps({'schema_version': 1, 'benchmark_name': 'luda-recorded-decision-v1', 'cases': [self.case]}))
        self.assertEqual(runner.load_cases(path), [self.case])

    def test_malformed_events_are_preserved_and_detected(self):
        path = self.base / 'events.jsonl'
        path.write_text('not JSON\n{"type":"turn.failed","error":"failure"}\n')
        result = runner.inspect_events(path)
        self.assertEqual(result['invalid_event_lines'], 1)
        self.assertEqual(len(result['errors']), 1)

    def test_reference_count_is_required(self):
        (self.skill / 'references/setup.md').unlink()
        with self.assertRaises(ValueError):
            runner.context_text(self.skill)


if __name__ == '__main__':
    unittest.main()
