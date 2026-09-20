"""Setup lifecycle tests use temporary profiles; never modify real client profiles."""
import contextlib
import io
import json
import os
from pathlib import Path
import pwd
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
        self.command = ['/opt/luda/current/.venv/bin/luda-session', '--user', 'example', '--', '/opt/luda/current/.venv/bin/luda']

    def plan(self, names=('codex',), **kwargs):
        return setup.plan_setup(names, self.home, self.source, self.command, environ={}, **kwargs)

    def install(self, names=('codex',), **kwargs):
        changes, destinations = self.plan(names, **kwargs)
        setup.apply_changes(changes)
        return destinations

    def test_first_install_and_repeat_are_idempotent(self):
        destinations = self.install()
        config, skill = destinations[0][1:]
        self.assertEqual((skill / 'SKILL.md').read_text(), 'instructions v1')
        self.assertTrue(config.is_file())
        changes, _ = self.plan()
        self.assertEqual(setup.apply_changes(changes), 0)

    def test_installs_every_selected_client_and_shared_skill(self):
        self.install(tuple(CLIENTS))
        changes, _ = self.plan(tuple(CLIENTS))
        self.assertEqual(setup.apply_changes(changes), 0)
        self.assertTrue((self.home / '.copilot/skills/luda/SKILL.md').is_file())

    def test_project_scope_does_not_write_user_agent_config(self):
        project = self.base / 'project'
        project.mkdir()
        self.install(('claude-code', 'copilot-cli'), scope='project', project=project)
        self.assertTrue((project / '.mcp.json').is_file())
        self.assertFalse((self.home / '.claude.json').exists())
        self.assertTrue((project / '.claude/skills/luda/SKILL.md').is_file())
        self.assertTrue((project / '.github/skills/luda/SKILL.md').is_file())

    def test_owned_skill_upgrade_changes_and_removes_files(self):
        destination = self.install()[0][2]
        (self.source / 'SKILL.md').write_text('instructions v2')
        (self.source / 'references/guide.md').unlink()
        (self.source / 'new.md').write_text('new reference')
        self.install()
        self.assertEqual((destination / 'SKILL.md').read_text(), 'instructions v2')
        self.assertFalse((destination / 'references/guide.md').exists())
        self.assertEqual((destination / 'new.md').read_text(), 'new reference')

    def test_edited_skill_upgrade_refuses_all_changes(self):
        config, destination = self.install()[0][1:]
        previous = config.read_bytes()
        (destination / 'SKILL.md').write_text('user edited')
        (self.source / 'SKILL.md').write_text('instructions v2')
        with self.assertRaisesRegex(ValueError, 'edited'):
            self.plan()
        self.assertEqual(config.read_bytes(), previous)
        self.assertEqual((destination / 'SKILL.md').read_text(), 'user edited')

    def test_unmanaged_different_skill_refuses(self):
        dest = self.home / '.agents/skills/luda'
        dest.mkdir(parents=True)
        (dest / 'SKILL.md').write_text('mine')
        with self.assertRaisesRegex(ValueError, 'unmanaged'):
            self.plan()
        self.assertFalse((self.home / '.codex/config.toml').exists())

    def test_existing_identical_skill_can_be_adopted(self):
        dest = self.home / '.agents/skills/luda'
        import shutil
        shutil.copytree(self.source, dest)
        self.install()
        self.assertEqual(setup.apply_changes(self.plan()[0]), 0)

    def test_unrelated_user_config_edits_preserved_on_repeat(self):
        config = self.install()[0][1]
        with config.open('a') as stream:
            stream.write('\n[unrelated]\nvalue = 42\n')
        original = config.read_bytes()
        self.install()
        self.assertEqual(config.read_bytes(), original)

    def test_different_luda_registration_refuses_before_skill_write(self):
        config = self.home / '.codex/config.toml'
        config.parent.mkdir()
        config.write_text('[mcp_servers.luda]\ncommand="my-own-server"\n')
        with self.assertRaisesRegex(ValueError, 'different luda'):
            self.plan()
        self.assertFalse((self.home / '.agents').exists())

    def test_concurrent_edit_before_apply_refuses_without_other_writes(self):
        changes, _ = self.plan()
        config = self.home / '.codex/config.toml'
        config.parent.mkdir()
        config.write_text('# editor changed this')
        with self.assertRaisesRegex(ValueError, 'changed during setup'):
            setup.apply_changes(changes)
        self.assertFalse((self.home / '.agents').exists())

    def test_write_failure_rolls_back_prior_files(self):
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
        self.assertFalse(two.exists())

    def test_rollback_does_not_overwrite_concurrent_edit(self):
        one, two = self.base / 'one', self.base / 'two'
        original = setup.atomic_write
        def fail(path, data):
            if path == two:
                one.write_bytes(b'editor')
                raise OSError('injected write error')
            return original(path, data)
        with patch.object(setup, 'atomic_write', side_effect=fail), self.assertRaises(OSError):
            setup.apply_changes([setup.Change(one, None, b'new'), setup.Change(two, None, b'new')])
        self.assertEqual(one.read_bytes(), b'editor')

    def test_symlinked_destination_refused(self):
        (self.home / '.codex').symlink_to(self.source, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, 'symlink'):
            self.plan()
        self.assertFalse((self.source / 'config.toml').exists())

    def test_export_bundle_contains_complete_skill_and_argv(self):
        export = self.base / 'export'
        setup.export_bundle(export, self.source, self.command)
        mcp = json.loads((export / 'mcp.json').read_text())['mcpServers']['luda']
        self.assertEqual([mcp['command'], *mcp['args']], self.command)
        self.assertEqual((export / 'skills/luda/references/guide.md').read_text(), 'reference v1')
        with self.assertRaisesRegex(ValueError, 'already exists'):
            setup.export_bundle(export, self.source, self.command)

    def test_custom_codex_and_xdg_config_locations(self):
        custom = self.base / 'custom'
        config, skill = setup.client_paths(CLIENTS['codex'], self.home, 'user', environ={'CODEX_HOME': str(custom)})
        self.assertEqual(config, custom / 'config.toml')
        self.assertEqual(skill, self.home / '.agents/skills/luda')
        config, skill = setup.client_paths(CLIENTS['opencode'], self.home, 'user', environ={'XDG_CONFIG_HOME': str(custom)})
        self.assertEqual(config, custom / 'opencode/opencode.json')
        self.assertEqual(skill, custom / 'opencode/skills/luda')
        with self.assertRaises(ValueError):
            setup.client_paths(CLIENTS['codex'], self.home, 'user', environ={'CODEX_HOME': 'relative'})

    def test_copilot_home_override(self):
        custom = self.base / 'copilot-profile'
        config, skill = setup.client_paths(CLIENTS['copilot-cli'], self.home, 'user', environ={'COPILOT_HOME': str(custom)})
        self.assertEqual(config, custom / 'mcp-config.json')
        self.assertEqual(skill, custom / 'skills/luda')

    def test_existing_opencode_jsonc_selected(self):
        config_dir = self.home / '.config/opencode'
        config_dir.mkdir(parents=True)
        existing = config_dir / 'opencode.jsonc'
        existing.write_text('{/* existing */}')
        config, _ = setup.client_paths(CLIENTS['opencode'], self.home, 'user', environ={})
        self.assertEqual(config, existing)
        self.install(('opencode',))
        self.assertIn('/* existing */', existing.read_text())
        self.assertFalse((config_dir / 'opencode.json').exists())

    def test_list_agents_needs_no_account_or_runtime(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            setup.main(['--list-agents'])
        for name in CLIENTS:
            self.assertIn(name, output.getvalue())
        self.assertIn('--export', output.getvalue())

    def test_project_opencode_preserves_existing_jsonc(self):
        project = self.base / 'project'
        project.mkdir()
        existing = project / 'opencode.jsonc'
        existing.write_text('{/* existing project */ "theme":"dark"}')
        self.install(('opencode',), scope='project', project=project)
        self.assertIn('/* existing project */', existing.read_text())
        self.assertFalse((project / 'opencode.json').exists())

    def test_root_requires_explicit_account(self):
        with patch.object(os, 'getuid', return_value=0), self.assertRaisesRegex(ValueError, 'Root must specify'):
            setup.validate(setup.parser().parse_args(['--agent', 'codex']))

    def test_unknown_client_and_nonexistent_account_explain_next_step(self):
        account = pwd.struct_passwd(('example', '', os.getuid(), os.getgid(), '', str(self.home), '/bin/sh'))
        with patch.object(pwd, 'getpwnam', return_value=account), self.assertRaisesRegex(ValueError, 'Unknown agent'):
            setup.validate(setup.parser().parse_args(['--user', 'example', '--agent', 'not-supported']))
        with patch.object(pwd, 'getpwnam', side_effect=KeyError), self.assertRaisesRegex(ValueError, 'does not exist'):
            setup.validate(setup.parser().parse_args(['--user', 'missing']))

    def cli_fixture(self):
        import shutil
        prefix = self.base / 'runtime'
        bindir = prefix / 'current/.venv/bin'
        bindir.mkdir(parents=True)
        for name in ('luda', 'luda-session'):
            path = bindir / name
            path.write_text('#!/bin/sh\nexit 0\n')
            path.chmod(0o755)
        shutil.copytree(self.source, prefix / 'current/skills/luda')
        account = pwd.struct_passwd(('example', '', os.getuid(), os.getgid(), '', str(self.home), '/bin/sh'))
        return account, ['--prefix', str(prefix), '--user', 'example', '--agent', 'codex', '--yes']

    def test_runtime_timeout_does_not_configure_agent(self):
        account, args = self.cli_fixture()
        with patch.object(pwd, 'getpwnam', return_value=account), patch.dict(os.environ, {}, clear=True), \
             patch.object(subprocess, 'run', side_effect=subprocess.TimeoutExpired('version', 20)), \
             contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as caught:
            setup.main(args)
        self.assertEqual(caught.exception.code, 1)
        self.assertFalse((self.home / '.codex').exists())

    def test_desktop_timeout_reports_failure_but_retains_completed_configuration(self):
        account, args = self.cli_fixture()
        effects = [subprocess.CompletedProcess('version', 0), subprocess.TimeoutExpired('doctor', 35)]
        with patch.object(pwd, 'getpwnam', return_value=account), patch.dict(os.environ, {}, clear=True), \
             patch.object(subprocess, 'run', side_effect=effects) as runner, \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()), \
             self.assertRaises(SystemExit) as caught:
            setup.main([*args, '--check-desktop'])
        self.assertEqual(caught.exception.code, 1)
        self.assertTrue((self.home / '.codex/config.toml').is_file())
        self.assertTrue((self.home / '.agents/skills/luda/SKILL.md').is_file())
        self.assertEqual(runner.call_args.kwargs['timeout'], 35)

    @unittest.skipUnless(os.getuid() == 0, 'root required for real UID drop test')
    def test_root_writes_as_selected_account_in_subprocess(self):
        accounts = [p for p in pwd.getpwall() if 1000 <= p.pw_uid < 60000]
        if not accounts:
            self.skipTest('No ordinary account available for isolated ownership test')
        account = accounts[0]
        self.base.chmod(0o755)
        os.chown(self.home, account.pw_uid, account.pw_gid)
        prefix = self.base / 'runtime'
        bindir = prefix / 'current/.venv/bin'
        bindir.mkdir(parents=True)
        for name in ('luda', 'luda-session'):
            path = bindir / name
            path.write_text('#!/bin/sh\nexit 0\n')
            path.chmod(0o755)
        import shutil
        shutil.copytree(self.source, prefix / 'current/skills/luda')
        script = 'import pwd; from luda import setup; account=pwd.getpwnam(%r); pwd.getpwnam=lambda name: pwd.struct_passwd((*account[:5], %r, account.pw_shell)); setup.main(%r)' % (account.pw_name, str(self.home), ['--prefix', str(prefix), '--user', account.pw_name, '--agent', 'codex', '--yes'])
        environment = dict(os.environ, PYTHONPATH=str(Path(setup.__file__).parents[1]))
        result = subprocess.run([sys.executable, '-c', script], env=environment, capture_output=True, text=True, timeout=15)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for path in self.home.rglob('*'):
            self.assertEqual(path.stat().st_uid, account.pw_uid, str(path))
        config = (self.home / '.codex/config.toml').read_text()
        self.assertIn(account.pw_name, config)
        self.assertIn(str(prefix / 'current/.venv/bin/luda'), config)


if __name__ == '__main__':
    unittest.main()
