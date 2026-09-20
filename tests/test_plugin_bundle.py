import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('build_plugin', ROOT / 'scripts/build_plugin.py')
plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin)


class PluginBundleTests(unittest.TestCase):
    def test_repository_manifest_and_launch_config(self):
        manifest = json.loads((ROOT / '.codex-plugin/plugin.json').read_text())
        self.assertEqual(manifest['name'], 'luda')
        self.assertTrue((ROOT / manifest['skills'] / 'luda/SKILL.md').is_file())
        self.assertEqual(json.loads((ROOT / manifest['mcpServers']).read_text()), {'mcpServers': {'luda': {'command': 'luda', 'args': []}}})

    def test_custom_prefix_is_literal_argv_and_remote_is_explicit(self):
        server = plugin.mcp_config('/tmp/guest prefix $(literal)', user='desktop', remote=True)['mcpServers']['luda']
        self.assertEqual(server['command'], '/tmp/guest prefix $(literal)/current/.venv/bin/luda-session')
        self.assertEqual(server['experimental_environment'], 'remote')
        self.assertEqual(server['args'][:3], ['--user', 'desktop', '--'])
        self.assertNotIn('experimental_environment', plugin.mcp_config('/opt/luda')['mcpServers']['luda'])

    def test_invalid_prefix_and_account(self):
        for prefix in ('/', 'relative', '/tmp/../bad', '/tmp/\ninvalid', '/tmp/~invalid'):
            with self.subTest(prefix=prefix), self.assertRaises(ValueError):
                plugin.mcp_config(prefix)
        for user in ('--root', 'two words', 'root\n'):
            with self.subTest(user=user), self.assertRaises(ValueError):
                plugin.mcp_config('/opt/luda', user)

    def test_bundle_is_self_contained_and_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'luda'
            plugin.build(output, '/guest/luda')
            self.assertEqual((output / 'skills/luda/SKILL.md').read_bytes(), (ROOT / 'skills/luda/SKILL.md').read_bytes())
            expected_skill = {p.relative_to(ROOT / 'skills/luda'): p.read_bytes() for p in (ROOT / 'skills/luda').rglob('*') if p.is_file()}
            actual_skill = {p.relative_to(output / 'skills/luda'): p.read_bytes() for p in (output / 'skills/luda').rglob('*') if p.is_file()}
            self.assertEqual(actual_skill, expected_skill)
            self.assertFalse(any(p.is_symlink() for p in output.rglob('*')))
            (output / 'user.txt').write_text('preserve')
            with self.assertRaises(FileExistsError):
                plugin.build(output, '/another/path')
            self.assertEqual((output / 'user.txt').read_text(), 'preserve')

    def test_failed_copy_leaves_no_partial_bundle(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'luda'
            with patch.object(plugin.shutil, 'copytree', side_effect=OSError('fixture failure')):
                with self.assertRaises(OSError):
                    plugin.build(output, '/opt/luda')
            self.assertFalse(output.exists())
            self.assertEqual(list(Path(directory).iterdir()), [])

    @unittest.skipUnless(shutil.which('codex'), 'Codex CLI not installed')
    def test_real_cli_registration_in_temporary_config(self):
        with tempfile.TemporaryDirectory(prefix='luda-plugin-test-') as directory:
            root = Path(directory)
            market = root / 'market'
            plugin.build_marketplace(market, '/opt/luda')
            private_config = root / 'codex-config'
            private_config.mkdir()
            env = {**os.environ, 'CODEX_HOME': str(private_config)}
            def codex(*args):
                result = subprocess.run([shutil.which('codex'), *args, '--json'], env=env, capture_output=True, text=True, timeout=30)
                self.assertEqual(result.returncode, 0, result.stderr)
                return json.loads(result.stdout)
            codex('plugin', 'marketplace', 'add', str(market))
            installed = codex('plugin', 'add', 'luda@luda-local')
            self.assertTrue(Path(installed['installedPath']).is_relative_to(private_config))
            cached = Path(installed['installedPath'])
            self.assertEqual(json.loads((cached / '.mcp.json').read_text()), plugin.mcp_config('/opt/luda'))
            self.assertTrue((cached / 'skills/luda/SKILL.md').is_file())
            self.assertTrue(codex('plugin', 'list')['installed'][0]['enabled'])


if __name__ == '__main__':
    unittest.main()
