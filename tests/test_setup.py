"""The wrapper delegates writes; real upstream preservation checks run separately."""
import contextlib
import io
import json
import os
from pathlib import Path
import pwd
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from luda import setup
from luda.setup_clients import CLIENTS


class SetupTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.home = self.base / 'home'
        self.home.mkdir()
        self.source = self.base / 'skill'
        self.source.mkdir()
        (self.source / 'SKILL.md').write_text('instructions v1')
        (self.source / 'references').mkdir()
        (self.source / 'references/guide.md').write_text('reference v1')
        self.prefix = self.base / 'runtime with spaces'
        self.tools = self.prefix / 'current/agent-tools'
        for relative in ('node/bin/node', 'node_modules/skills/bin/cli.mjs',
                         'node_modules/add-mcp/dist/index.js'):
            target = self.tools / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text('')
        self.node = self.tools / 'node/bin/node'
        self.node.write_text('''#!/usr/bin/python3
import json, os, pathlib, sys
home = pathlib.Path(os.environ['HOME'])
with (home / 'calls.jsonl').open('a') as f:
    f.write(json.dumps({'argv': sys.argv[1:], 'cwd': os.getcwd(), 'home': str(home),
                       'uid': os.getuid(), 'codex_home': os.environ.get('CODEX_HOME')}) + '\\n')
if 'skills' in sys.argv[1]:
    print('[{"name":"luda","status":"installed"}]')
''')
        self.node.chmod(0o755)
        self.bindir = self.prefix / 'current/.venv/bin'
        self.bindir.mkdir(parents=True)
        for name in ('luda', 'luda-session'):
            path = self.bindir / name
            path.write_text('#!/bin/sh\nexit 0\n')
            path.chmod(0o755)
        shutil.copytree(self.source, self.prefix / 'current/skills/luda')
        self.command = [str(self.bindir / 'luda-session'), '--user', 'example', '--', str(self.bindir / 'luda')]
        self.account = pwd.struct_passwd(('example', '', os.getuid(), os.getgid(), '', str(self.home), '/bin/sh'))
        self.args = ['--prefix', str(self.prefix), '--user', 'example', '--agent', 'codex', '--yes']

    def configure(self, names=('codex',), **kwargs):
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return setup.configure(names, self.home, self.source, self.command, self.tools, environ={}, **kwargs)

    def calls(self):
        return [json.loads(line) for line in (self.home / 'calls.jsonl').read_text().splitlines()]

    def main(self, args=None):
        with patch.object(pwd, 'getpwnam', return_value=self.account), patch.dict(os.environ, {}, clear=True), \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            return setup.main(self.args if args is None else args)

    def test_explicit_absent_agent_uses_local_upstreams_and_separate_argv(self):
        self.assertEqual(self.configure(), [])
        skill, mcp = self.calls()
        self.assertIn('--copy', skill['argv'])
        self.assertIn('--json', skill['argv'])
        self.assertIn(str(self.source), skill['argv'])
        self.assertIn('--global', skill['argv'])
        self.assertIn(self.command[0], mcp['argv'])
        for arg in self.command[1:]:
            self.assertIn('--args=' + arg, mcp['argv'])
        self.assertEqual(skill['home'], str(self.home))
        self.assertEqual(skill['cwd'], str(self.home))
        self.assertFalse((self.home / '.codex').exists(), 'wrapper must not write client configuration')

    def test_every_selected_client_passes_explicit_upstream_names(self):
        self.assertEqual(self.configure(list(CLIENTS)), [])
        calls = self.calls()
        self.assertEqual(len(calls), 14)
        for index, client in enumerate(CLIENTS.values()):
            for call, expected in zip(calls[index*2:index*2+2], (client.skills_agent, client.mcp_agent)):
                self.assertEqual(call['argv'][call['argv'].index('--agent') + 1], expected)

    def test_project_scope_uses_project_cwd_without_global(self):
        project = self.base / 'project'
        project.mkdir()
        self.assertEqual(self.configure(scope='project', project=project), [])
        for call in self.calls():
            self.assertEqual(call['cwd'], str(project))
            self.assertNotIn('--global', call['argv'])

    def test_repeat_delegates_same_requests(self):
        self.configure()
        self.configure()
        calls = self.calls()
        self.assertEqual(calls[:2], calls[2:])

    def test_special_characters_are_never_shell_interpreted(self):
        self.command += ['$(touch /tmp/not-run)', '`id`', '--flag=value', "single'quote"]
        self.assertEqual(self.configure(), [])
        self.assertEqual(self.calls()[1]['argv'][-4:], ['--args=' + a for a in self.command[-4:]])

    def test_failure_continues_other_phases_and_clients(self):
        ok_skill = subprocess.CompletedProcess([], 0, '[{"name":"luda","status":"installed"}]', '')
        failed = subprocess.CompletedProcess([], 1, '', 'cannot merge existing file')
        with patch.object(subprocess, 'run', side_effect=[ok_skill, failed, ok_skill, subprocess.CompletedProcess([], 0, '', '')]) as runner:
            failures = self.configure(('codex', 'claude-code'))
        self.assertEqual(runner.call_count, 4)
        self.assertEqual(failures[0][:2], ('codex', 'MCP'))
        self.assertIn('cannot merge', failures[0][2])

    def test_timeout_is_reported_and_next_phase_still_runs(self):
        with patch.object(subprocess, 'run', side_effect=[subprocess.TimeoutExpired('skills', 120), subprocess.CompletedProcess([], 0, '', '')]):
            failures = self.configure()
        self.assertEqual(failures[0][:2], ('codex', 'skill'))
        self.assertIn('120', failures[0][2])

    def test_success_exit_without_installed_skill_is_not_success(self):
        for output in ('[]', '{}', 'not json', '[{"name":"luda","status":"skipped"}]'):
            with self.subTest(output=output), patch.object(subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, output, '')):
                self.assertEqual(self.configure()[0][:2], ('codex', 'skill'))

    def test_missing_tools_prevents_all_registration(self):
        self.node.unlink()
        with self.assertRaisesRegex(ValueError, 'Bundled agent installer missing'):
            self.configure()
        self.assertFalse((self.home / 'calls.jsonl').exists())

    def test_missing_skill_prevents_all_registration(self):
        (self.source / 'SKILL.md').unlink()
        with self.assertRaisesRegex(ValueError, 'Complete Luda skill missing'):
            self.configure()
        self.assertFalse((self.home / 'calls.jsonl').exists())

    def test_supported_profile_overrides_and_telemetry_disabled(self):
        env = setup.installer_environment(self.home, ['codex', 'opencode'], {
            'CODEX_HOME': str(self.base / 'codex'), 'XDG_CONFIG_HOME': str(self.base / 'config'),
            'NODE_OPTIONS': '--require malicious', 'NODE_PATH': '/foreign'})
        self.assertEqual(env['CODEX_HOME'], str(self.base / 'codex'))
        self.assertEqual(env['XDG_CONFIG_HOME'], str(self.base / 'config'))
        self.assertEqual(env['DO_NOT_TRACK'], '1')
        self.assertNotIn('NODE_OPTIONS', env)
        self.assertNotIn('NODE_PATH', env)

    def test_unsupported_selected_profile_overrides_fail_before_writes(self):
        cases = [('copilot-cli', 'COPILOT_HOME'), ('copilot-cli', 'XDG_CONFIG_HOME'),
                 ('claude-code', 'CLAUDE_CONFIG_DIR'), ('gemini-cli', 'GEMINI_CLI_HOME'),
                 ('opencode', 'OPENCODE_CONFIG'), ('opencode', 'OPENCODE_CONFIG_DIR')]
        for agent, variable in cases:
            with self.subTest(variable=variable), self.assertRaisesRegex(ValueError, variable):
                setup.installer_environment(self.home, [agent], {variable: '/custom'})
        setup.installer_environment(self.home, ['codex'], {'COPILOT_HOME': '/unrelated'})

    def test_relative_supported_override_rejected(self):
        with self.assertRaisesRegex(ValueError, 'must be absolute'):
            setup.installer_environment(self.home, ['codex'], {'CODEX_HOME': 'relative'})

    def test_all_selection_expands_without_detection(self):
        with patch.object(pwd, 'getpwnam', return_value=self.account):
            _, names = setup.validate(setup.parser().parse_args(['--user', 'example', '--agent', 'all']))
        self.assertEqual(names, list(CLIENTS))

    def test_exclusive_auto_and_all_and_alias_deduplication(self):
        with patch.object(pwd, 'getpwnam', return_value=self.account):
            for names in (['all', 'codex'], ['auto', 'all'], ['auto', 'codex']):
                with self.assertRaisesRegex(ValueError, 'alone'):
                    setup.validate(setup.parser().parse_args(['--user', 'example', *sum((['--agent', n] for n in names), [])]))
            _, names = setup.validate(setup.parser().parse_args(['--user', 'example', '--agent', 'claude', '--agent', 'claude-code']))
            self.assertEqual(names, ['claude-code'])

    def test_auto_detects_leftover_config_without_executable(self):
        (self.home / '.claude.json').write_text('{}')
        with patch.object(shutil, 'which', return_value=None):
            self.assertEqual(setup.detect(self.home), ['claude-code'])

    def test_root_requires_explicit_account(self):
        with patch.object(os, 'getuid', return_value=0), self.assertRaisesRegex(ValueError, 'Root must specify'):
            setup.validate(setup.parser().parse_args(['--agent', 'codex']))

    def test_unknown_client_and_missing_account_explain_problem(self):
        with patch.object(pwd, 'getpwnam', return_value=self.account), self.assertRaisesRegex(ValueError, 'Unknown agent'):
            setup.validate(setup.parser().parse_args(['--user', 'example', '--agent', 'unknown']))
        with patch.object(pwd, 'getpwnam', side_effect=KeyError), self.assertRaisesRegex(ValueError, 'does not exist'):
            setup.validate(setup.parser().parse_args(['--user', 'missing']))

    def test_list_agents_needs_no_runtime_or_account(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            setup.main(['--list-agents'])
        for name in CLIENTS:
            self.assertIn(name, output.getvalue())

    def test_noninteractive_requires_selection_and_confirmation(self):
        for args in (self.args[:4], self.args[:-1]):
            with self.subTest(args=args), self.assertRaises(SystemExit) as caught:
                self.main(args)
            self.assertEqual(caught.exception.code, 1)
        self.assertFalse((self.home / 'calls.jsonl').exists())

    def test_main_failures_report_retry_with_only_failed_clients(self):
        stderr = io.StringIO()
        with patch.object(pwd, 'getpwnam', return_value=self.account), patch.dict(os.environ, {}, clear=True), \
             patch.object(setup, 'configure', return_value=[('codex', 'MCP', 'failure')]), \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(stderr), self.assertRaises(SystemExit):
            setup.main([*self.args, '--agent', 'claude-code'])
        self.assertIn('Completed steps remain', stderr.getvalue())
        self.assertIn('--agent codex', stderr.getvalue())
        self.assertNotIn('--agent claude-code', stderr.getvalue())

    def test_runtime_timeout_prevents_registration(self):
        with patch.object(subprocess, 'run', side_effect=subprocess.TimeoutExpired('version', 20)), self.assertRaises(SystemExit):
            self.main()
        self.assertFalse((self.home / 'calls.jsonl').exists())

    def test_desktop_timeout_retains_completed_registration(self):
        original = subprocess.run
        def run(argv, **kwargs):
            if argv[-1] == 'doctor':
                raise subprocess.TimeoutExpired(argv, 35)
            return original(argv, **kwargs)
        with patch.object(subprocess, 'run', side_effect=run), self.assertRaises(SystemExit):
            self.main([*self.args, '--check-desktop'])
        self.assertEqual(len(self.calls()), 2)

    def test_export_contains_complete_skill_and_argv_without_node(self):
        shutil.rmtree(self.tools)
        export = self.base / 'export'
        self.main([*self.args[:4], '--export', str(export), '--yes'])
        mcp = json.loads((export / 'mcp.json').read_text())['mcpServers']['luda']
        self.assertEqual([mcp['command'], *mcp['args']], self.command)
        self.assertEqual((export / 'skills/luda/references/guide.md').read_text(), 'reference v1')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            setup.export_bundle(export, self.source, self.command)

    def test_export_refuses_symlink_destination(self):
        link = self.base / 'link'
        link.symlink_to(self.source, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            setup.export_bundle(link / 'export', self.source, self.command)

    def test_export_write_failure_rolls_back_own_changes(self):
        one, two = self.base / 'one', self.base / 'two'
        one.write_bytes(b'old')
        original = setup.atomic_write
        def fail(path, data):
            if path == two:
                raise OSError('injected write error')
            return original(path, data)
        with patch.object(setup, 'atomic_write', side_effect=fail), self.assertRaises(OSError):
            setup.apply_changes([setup.Change(one, b'old', b'new'), setup.Change(two, None, b'new')])
        self.assertEqual(one.read_bytes(), b'old')

    @unittest.skipUnless(os.getuid() == 0, 'root required for real UID drop test')
    def test_root_runs_installers_as_selected_account_with_fresh_environment(self):
        accounts = [p for p in pwd.getpwall() if 1000 <= p.pw_uid < 60000]
        if not accounts:
            self.skipTest('No ordinary account available for isolated ownership test')
        account = accounts[0]
        self.base.chmod(0o755)
        os.chown(self.home, account.pw_uid, account.pw_gid)
        script = 'import pwd; from luda import setup; account=pwd.getpwnam(%r); pwd.getpwnam=lambda name: pwd.struct_passwd((*account[:5], %r, account.pw_shell)); setup.main(%r)' % (account.pw_name, str(self.home), [*self.args[:2], '--user', account.pw_name, *self.args[4:]])
        environment = dict(os.environ, PYTHONPATH=str(Path(setup.__file__).parents[1]), CODEX_HOME='/should-not-leak')
        result = subprocess.run([sys.executable, '-c', script], env=environment, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for path in self.home.rglob('*'):
            self.assertEqual(path.stat().st_uid, account.pw_uid, str(path))
        for call in self.calls():
            self.assertEqual(call['uid'], account.pw_uid)
            self.assertIsNone(call['codex_home'])


if __name__ == '__main__':
    unittest.main()
