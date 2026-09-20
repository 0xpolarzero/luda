import importlib.util
from pathlib import Path
import tempfile
import os
import shutil
import subprocess
import tomllib
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('install_skill', Path(__file__).parents[1] / 'scripts/install_skill.py')
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class SkillInstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source'
        (self.source / 'references').mkdir(parents=True)
        (self.source / 'SKILL.md').write_text('skill')
        (self.source / 'references/setup.md').write_text('setup')

    def test_all_user_profiles_copy_references_preserve_unrelated_and_repeat(self):
        for agent, relative in module.LOCATIONS.items():
            home = self.root / agent
            unrelated = home / relative / 'other/SKILL.md'
            unrelated.parent.mkdir(parents=True)
            unrelated.write_text('keep')
            target, created = module.install(agent, 'user', self.source, home=home)
            self.assertTrue(created)
            self.assertEqual(target, home / relative / 'luda')
            self.assertEqual((target / 'references/setup.md').read_text(), 'setup')
            self.assertEqual(unrelated.read_text(), 'keep')
            self.assertFalse(module.install(agent, 'user', self.source, home=home)[1])

    def test_project_scope_does_not_touch_home(self):
        for agent in module.LOCATIONS:
            project = self.root / agent
            target, _ = module.install(agent, 'project', self.source, project=project, home=self.root / 'home')
            expected = '.opencode/skills' if agent == 'opencode' else module.LOCATIONS[agent]
            self.assertEqual(target, project / expected / 'luda')
        self.assertFalse((self.root / 'home').exists())

    def test_modified_or_extra_files_refuse_without_changes(self):
        target, _ = module.install('claude', 'user', self.source, home=self.root)
        (target / 'personal.md').write_text('keep')
        with self.assertRaises(FileExistsError):
            module.install('claude', 'user', self.source, home=self.root)
        self.assertEqual((target / 'personal.md').read_text(), 'keep')

    def test_symlink_source_and_destination_refused(self):
        link = self.root / 'link'
        link.symlink_to(self.source, target_is_directory=True)
        with self.assertRaises(ValueError):
            module.install('codex', 'user', link, home=self.root)
        target = self.root / '.agents/skills/luda'
        target.parent.mkdir(parents=True)
        target.symlink_to(self.source, target_is_directory=True)
        with self.assertRaises(FileExistsError):
            module.install('codex', 'user', self.source, home=self.root)

    def test_nested_symlink_refused(self):
        (self.source / 'references/link').symlink_to(self.source / 'SKILL.md')
        with self.assertRaises(ValueError):
            module.install('codex', 'user', self.source, home=self.root)

    def test_explicit_scope_and_xdg_configuration(self):
        with self.assertRaises(ValueError):
            module.install('codex', 'user', self.source, project=self.root)
        with patch.dict('os.environ', {'XDG_CONFIG_HOME': str(self.root / 'xdg')}):
            target, _ = module.install('opencode', 'user', self.source)
            self.assertEqual(target, self.root / 'xdg/opencode/skills/luda')

    def test_failed_copy_leaves_no_partial_installation(self):
        original = module.shutil.copytree
        def fail_final(source, destination, *args, **kwargs):
            if kwargs.get('dirs_exist_ok'):
                (destination / 'partial').write_text('partial')
                raise OSError('disk failure')
            return original(source, destination, *args, **kwargs)
        with patch.object(module.shutil, 'copytree', side_effect=fail_final):
            with self.assertRaises(OSError):
                module.install('codex', 'user', self.source, home=self.root)
        self.assertEqual(list((self.root / '.agents/skills').iterdir()), [])

    @unittest.skipUnless(shutil.which('codex'), 'Codex CLI not installed')
    def test_documented_codex_registration_preserves_other_configuration(self):
        profile = self.root / 'codex-profile'
        profile.mkdir()
        (profile / 'config.toml').write_text('[mcp_servers.other]\ncommand="/keep/me"\n')
        environment = {**os.environ, 'CODEX_HOME': str(profile)}
        result = subprocess.run([shutil.which('codex'), 'mcp', 'add', 'luda', '--',
                                 '/opt/luda/current/.venv/bin/luda'],
                                env=environment, capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        config = tomllib.loads((profile / 'config.toml').read_text())
        self.assertEqual(config['mcp_servers']['other']['command'], '/keep/me')
        self.assertEqual(config['mcp_servers']['luda']['command'], '/opt/luda/current/.venv/bin/luda')
