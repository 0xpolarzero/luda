import importlib.util
import json
from pathlib import Path
import tempfile
import sys
import time
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('manage_install', Path(__file__).resolve().parents[1] / 'scripts/manage_install.py')
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class Installation(unittest.TestCase):
    def setUp(self):
        for name in ('check_install_access', 'verify_desktop_access'):
            stub = patch.object(installer, name)
            stub.start(); self.addCleanup(stub.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.prefix = self.root / 'installation'
        self.source = self.root / 'source'
        self.source.mkdir()
        (self.source / 'pyproject.toml').write_text('[project]\nname="luda"\nversion="1.0.0"\n')
        (self.source / 'requirements.lock').write_text('fixture lock')
        (self.source / 'build-requirements.lock').write_text('fixture build lock')
        (self.source / 'MANIFEST.in').write_text('fixture manifest')
        (self.source / 'src').mkdir()
        (self.source / 'src/file.py').write_text('fixture')
        (self.source / 'skills/luda').mkdir(parents=True)
        (self.source / 'skills/luda/SKILL.md').write_text('fixture skill')
        self.commands = []

    def runner(self, command):
        args = list(map(str, command))
        self.commands.append(args)
        if args[1:4] == ['-I', '-m', 'venv']:
            path = Path(args[4]) / 'bin'
            path.mkdir(parents=True)
            (path / 'python').write_text('fixture interpreter')
        elif 'wheel' in args:
            path = Path(args[args.index('--wheel-dir') + 1])
            path.mkdir()
            (path / 'luda-1.0.0-py3-none-any.whl').write_text('fixture wheel')

    def test_prefix_validation(self):
        for value in ['relative', '/', '/usr', '/home', '/tmp/../opt/luda', '/tmp/bad\npath']:
            with self.subTest(value=value), self.assertRaises(installer.InstallError):
                installer.checked_prefix(value)
        link = self.root / 'alias'
        link.symlink_to(self.source, target_is_directory=True)
        with self.assertRaises(installer.InstallError):
            installer.checked_prefix(str(link / 'install'))

    def test_repeat_install_is_noop_with_stable_release(self):
        first = installer.install(self.prefix, self.source, self.runner)
        commands = len(self.commands)
        second = installer.install(self.prefix, self.source, self.runner)
        self.assertEqual(first['release'], second['release'])
        self.assertEqual(second['status'], 'already_installed')
        self.assertEqual(len(self.commands), commands)
        self.assertIn('--require-hashes', self.commands[1])
        self.assertIn('--require-hashes', self.commands[2])
        self.assertIn('--no-build-isolation', self.commands[3])

    def test_packaged_source_changes_alter_release_identity(self):
        previous=installer.release_identity(self.source)
        for name in ('.mcp.json','.codex-plugin/plugin.json','scripts/manage_install.py','docs/example.md','tests/fixtures/page.html','tests/fixtures/editor/package-lock.json','tests/fixtures/editor/THIRD_PARTY_NOTICES.md','integrations/prosemirror/luda-prosemirror.mjs'):
            path=self.source/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('package content')
            current=installer.release_identity(self.source)
            self.assertNotEqual(previous,current);previous=current
        cache=self.source/'src/__pycache__/generated.pyc';cache.parent.mkdir();cache.write_bytes(b'cache')
        self.assertEqual(previous,installer.release_identity(self.source))
        dependency=self.source/'tests/tools/codex-cli/node_modules/example/index.js'
        dependency.parent.mkdir(parents=True);dependency.write_text('installed dependency')
        self.assertEqual(previous,installer.release_identity(self.source))
        dependency.write_text('different installed dependency')
        self.assertEqual(previous,installer.release_identity(self.source))

    def test_source_mutation_during_build_preserves_prior_release(self):
        first=installer.install(self.prefix,self.source,self.runner)
        (self.source/'src/file.py').write_text('upgrade')
        def changing(command):
            self.runner(command)
            if 'wheel' in list(map(str,command)):
                (self.source/'skills/luda/SKILL.md').write_text('changed during build')
        with self.assertRaisesRegex(installer.InstallError,'Source changed'):
            installer.install(self.prefix,self.source,changing)
        self.assertEqual((self.prefix/'current').readlink().name,first['release'])
        self.assertEqual(len(list((self.prefix/'releases').iterdir())),1)

    def test_failed_upgrade_preserves_selected_release_and_retry(self):
        first = installer.install(self.prefix, self.source, self.runner)
        (self.source / 'src/file.py').write_text('new release')
        def failing(args):
            raise installer.InstallError('injected dependency failure')
        with self.assertRaises(installer.InstallError):
            installer.install(self.prefix, self.source, failing)
        self.assertEqual((self.prefix / 'current').readlink().name, first['release'])
        second = installer.install(self.prefix, self.source, self.runner)
        self.assertNotEqual(first['release'], second['release'])
        installer.rollback(self.prefix, first['release'])
        self.assertEqual((self.prefix / 'current').readlink().name, first['release'])

    def test_first_install_failure_can_be_retried(self):
        with self.assertRaises(installer.InstallError):
            installer.install(self.prefix, self.source, lambda _: (_ for _ in ()).throw(installer.InstallError('failed')))
        installer.install(self.prefix, self.source, self.runner)
        self.assertTrue((self.prefix / 'current').is_dir())

    def test_uninstall_preserves_user_files_and_modified_installed_files(self):
        first = installer.install(self.prefix, self.source, self.runner)
        (self.prefix / 'personal.txt').write_text('preserve outside release')
        release = self.prefix / 'releases' / first['release']
        (release / 'notes.txt').write_text('preserve unknown file')
        skill = release / 'skills/luda/SKILL.md'
        skill.write_text('preserve modified skill')
        result = installer.uninstall(self.prefix)
        self.assertEqual(result['retained_modified_releases'], [first['release']])
        self.assertEqual(skill.read_text(), 'preserve modified skill')
        self.assertTrue((release / 'notes.txt').exists())
        self.assertTrue((self.prefix / 'personal.txt').exists())
        self.assertFalse((self.prefix / 'current').exists())
        installer.uninstall(self.prefix)
        self.assertTrue((release / 'notes.txt').exists())
        installer.install(self.prefix, self.source, self.runner)
        archive = next((self.prefix / 'releases').glob('.interrupted-*'))
        self.assertEqual((archive / 'notes.txt').read_text(), 'preserve unknown file')

    def test_clean_uninstall_and_reinstall(self):
        installer.install(self.prefix, self.source, self.runner)
        self.assertEqual(installer.uninstall(self.prefix)['retained_modified_releases'], [])
        installer.install(self.prefix, self.source, self.runner)
        self.assertTrue((self.prefix / 'current').is_dir())

    def test_configuration_quotes_paths_and_never_overwrites(self):
        self.prefix = self.root / 'literal " path'
        installer.install(self.prefix, self.source, self.runner)
        output = self.root / 'configuration'
        installer.config(self.prefix, output, 'desktop')
        parsed = installer.tomllib.loads((output / 'config.toml.fragment').read_text())
        self.assertEqual(parsed['mcp_servers']['luda']['args'][1], 'desktop')
        self.assertEqual(parsed['mcp_servers']['luda']['command'], str(self.prefix / 'current/.venv/bin/luda-session'))
        with self.assertRaises(installer.InstallError):
            installer.config(self.prefix, output, 'desktop')
        self.assertEqual((output / '.agents/skills/luda/SKILL.md').read_text(), 'fixture skill')
        instructions=(output/'README.txt').read_text()
        self.assertIn('LOCAL PLACEMENT',instructions)
        self.assertIn('Codex running on the selected Linux machine',instructions)
        self.assertNotIn('REMOTE PLACEMENT:',instructions)

    def test_remote_unattended_config_is_explicit_and_parseable(self):
        installer.install(self.prefix,self.source,self.runner)
        output=self.root/'remote-config'
        result=installer.config(self.prefix,output,'desktop',tool_approval='approve',placement='remote')
        server=installer.tomllib.loads((output/'config.toml.fragment').read_text())['mcp_servers']['luda']
        self.assertEqual(server['default_tools_approval_mode'],'approve')
        self.assertEqual(server['experimental_environment'],'remote')
        self.assertTrue(server['required']);self.assertEqual(result['placement'],'remote')
        instructions=(output/'README.txt').read_text()
        self.assertIn('REMOTE PLACEMENT',instructions)
        self.assertIn('host Codex profile/project configuration',instructions)
        self.assertIn('does not create an SSH connection',instructions)
        self.assertNotIn('LOCAL PLACEMENT:',instructions)
        with self.assertRaises(installer.InstallError):installer.config(self.prefix,self.root/'bad','desktop',tool_approval='unknown')
        self.assertFalse((self.root/'bad').exists())

    def test_unknown_current_path_is_preserved(self):
        self.prefix.mkdir()
        (self.prefix / 'current').write_text('user content')
        with self.assertRaises(installer.InstallError):
            installer.install(self.prefix, self.source, self.runner)
        self.assertEqual((self.prefix / 'current').read_text(), 'user content')

    def test_interrupted_owned_build_is_archived_then_retried(self):
        identity = installer.release_identity(self.source)
        release = self.prefix / 'releases' / identity
        release.mkdir(parents=True)
        installer.atomic_json(self.prefix / installer.MARKER, {'product': 'luda', 'schema_version': 1, 'releases': []})
        installer.atomic_json(release / '.luda-release-owner.json', {'product': 'luda', 'release': identity})
        (release / 'debug.txt').write_text('preserve interrupted build')
        installer.install(self.prefix, self.source, self.runner)
        archived = list((self.prefix / 'releases').glob('.interrupted-*'))
        self.assertEqual(len(archived), 1)
        self.assertEqual((archived[0] / 'debug.txt').read_text(), 'preserve interrupted build')

    def test_manifest_traversal_does_not_delete_external_file(self):
        first = installer.install(self.prefix, self.source, self.runner)
        release = self.prefix / 'releases' / first['release']
        manifest = release / 'release.json'
        data = json.loads(manifest.read_text())
        data['files']['../../outside'] = {'sha256': 'forged'}
        manifest.write_text(json.dumps(data))
        with self.assertRaises(installer.InstallError):
            installer.uninstall(self.prefix)
        self.assertTrue((self.prefix / 'current').is_symlink())

    def test_second_installer_is_refused_without_waiting(self):
        with installer.locked(self.prefix):
            with self.assertRaisesRegex(installer.InstallError, 'Another installation'):
                installer.install(self.prefix, self.source, self.runner)
        self.assertEqual(self.commands, [])

    def test_missing_dependency_is_actionable(self):
        with self.assertRaisesRegex(installer.InstallError, 'Missing dependency'):
            installer.invoke(['/no-such-installer-command'])

    def test_timed_out_build_cannot_write_after_cleanup(self):
        sentinel = self.root / 'late-build-write'
        child = 'import pathlib,sys,time;time.sleep(.3);pathlib.Path(sys.argv[1]).write_text("late")'
        parent = 'import subprocess,sys,time;subprocess.Popen([sys.executable,"-c",sys.argv[1],sys.argv[2]]);time.sleep(30)'
        with self.assertRaisesRegex(installer.InstallError, 'timed out'):
            installer.invoke([sys.executable, '-c', parent, child, str(sentinel)], timeout=.1)
        time.sleep(.35)
        self.assertFalse(sentinel.exists())

    def test_modified_release_is_not_reused_or_rolled_back(self):
        first=installer.install(self.prefix,self.source,self.runner)
        (self.source/'src/file.py').write_text('upgrade')
        second=installer.install(self.prefix,self.source,self.runner)
        old=self.prefix/'releases'/first['release']
        (old/'skills/luda/SKILL.md').write_text('user modification')
        with self.assertRaisesRegex(installer.InstallError,'files changed'):
            installer.rollback(self.prefix,first['release'])
        self.assertEqual((self.prefix/'current').readlink().name,second['release'])
        (self.prefix/'current/skills/luda/SKILL.md').unlink()
        with self.assertRaisesRegex(installer.InstallError,'disappeared'):
            installer.install(self.prefix,self.source,self.runner)
        self.assertEqual((old/'skills/luda/SKILL.md').read_text(),'user modification')

    def test_payload_parent_symlink_refuses_selection(self):
        first=installer.install(self.prefix,self.source,self.runner)
        release=self.prefix/'releases'/first['release']
        skill=release/'skills/luda';skill.rename(release/'retained-skill');skill.symlink_to(release/'retained-skill')
        with self.assertRaisesRegex(installer.InstallError,'parent became a symlink'):
            installer.rollback(self.prefix,first['release'])
        self.assertTrue(skill.is_symlink())

    def test_unknown_rollback_is_refused(self):
        installer.install(self.prefix, self.source, self.runner)
        with self.assertRaises(installer.InstallError):
            installer.rollback(self.prefix, '../../outside')


if __name__ == '__main__':
    unittest.main()
