"""Orchestration contracts; actual fixture transitions have separate tests."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

DIRECTORY = Path(__file__).resolve().parents[1] / 'scripts/evaluation'
sys.path.insert(0, str(DIRECTORY))
try:
    spec = importlib.util.spec_from_file_location('skill_interactions', DIRECTORY / 'skill_interactions.py')
    runner = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(runner)
finally:
    sys.path.remove(str(DIRECTORY))


class InteractionRunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.cli = self.base / 'codex'
        self.skill = DIRECTORY.parents[1] / 'skills/luda'

    def fake(self, extra=''):
        self.cli.write_text('''#!/usr/bin/env python3
import sys,json
from pathlib import Path
args=sys.argv
assert args[args.index('--model')+1]=='gpt-5.6-sol'
assert 'features.shell_tool=false' in args
assert 'mcp_servers.luda.default_tools_approval_mode="approve"' in args
assert not any('reasoning_effort' in a for a in args)
assert 'Change the setting through the GUI, not shell commands or code.' in sys.stdin.read()
Path(args[args.index('--output-last-message')+1]).write_text('The application is dark.')
for e in [{'type':'thread.started','thread_id':'fresh'}, {'type':'item.completed','item':{'type':'mcp_tool_call','server':'luda','tool':'desktop_observe'}}, {'type':'turn.completed'}]: print(json.dumps(e))
''' + extra)
        self.cli.chmod(0o700)

    def run_case(self, case='live-theme'):
        return runner.run_interaction(case, self.skill, self.base / 'out', str(self.cli), 3,
                                      self.base / 'auth', ['/fixture/server', '--private-args'])

    def test_live_recording_requires_separate_verification(self):
        self.fake()
        result = self.run_case()
        self.assertEqual(result['status'], 'recorded')
        self.assertEqual(result['semantic_grade'], 'ungraded')
        self.assertIn('Required separately', result['live_verification'])
        self.assertEqual(len(result['installed_skill_hashes']), 8)
        self.assertEqual((self.base / 'out/prompt.txt').read_text(), runner.APPEARANCE_TASK)
        self.assertNotIn('/private', (self.base / 'out/supplied-context.txt').read_text())

    def test_fixture_without_oracle_is_unassessable(self):
        self.fake()
        result = self.run_case('theme')
        self.assertEqual(result['status'], 'unassessable')
        self.assertIn('oracle_error', result)

    def test_fixture_state_preserved_without_semantic_pass(self):
        self.fake('''Path(args[args.index('--output-last-message')+1]).with_name('oracle.json').write_text(json.dumps({'state':{'selected':'Greybird-dark','applied':'Greybird'}}))
''')
        result = self.run_case('activation-no-effect')
        self.assertEqual(result['independent_state']['state']['applied'], 'Greybird')
        self.assertEqual(result['semantic_grade'], 'ungraded')

    def test_shell_is_disqualifying_even_with_final_answer(self):
        self.fake('''print(json.dumps({'type':'item.completed','item':{'type':'command_execution','command':'echo bad'}}))
''')
        result = self.run_case()
        self.assertEqual(result['status'], 'unassessable')
        self.assertFalse(result['gui_tools_only'])

    def test_selection_prompt_is_exact(self):
        self.assertEqual(runner.public_task('select-already'), runner.SELECTION_TASK)
        self.assertEqual(runner.public_task('select-only'), runner.SELECTION_TASK)
        with self.assertRaises(ValueError):
            runner.public_task('unknown')


if __name__ == '__main__':
    unittest.main()
