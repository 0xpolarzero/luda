"""Shell entrypoint contracts; no apt, downloads, or real account writes."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class InstallEntrypointTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.directory = Path(self.tmp.name)
        self.bin = self.directory / 'bin'
        self.bin.mkdir()
        self.prefix = self.directory / 'installed'
        self.log = self.directory / 'calls'
        # Mock only external processes, keeping the real shell parser and order.
        stub = '''#!/usr/bin/python3
import json, os, sys
with open(os.environ['INSTALL_CALLS'], 'a') as f:
    f.write(json.dumps([os.path.basename(sys.argv[0]), *sys.argv[1:]]) + '\\n')
if os.path.basename(sys.argv[0]) == 'id':
    print('0' if '-u' in sys.argv else 'root')
if '--validate-only' in sys.argv and os.environ.get('REJECT_SETUP'):
    sys.exit(2)
'''
        for name in ('python3', 'apt-get', 'id'):
            path = self.bin / name
            path.write_text(stub)
            path.chmod(0o755)
        installed_python = self.prefix / 'current/.venv/bin/python'
        installed_python.parent.mkdir(parents=True)
        installed_python.write_text(stub)
        installed_python.chmod(0o755)
        self.env = dict(os.environ, PATH=f'{self.bin}:/usr/bin:/bin', INSTALL_CALLS=str(self.log))

    def run_install(self, *args, reject=False):
        env = dict(self.env)
        if reject:
            env['REJECT_SETUP'] = '1'
        return subprocess.run(['bash', str(ROOT / 'scripts/install.sh'), *map(str, args)],
                              env=env, stdin=subprocess.DEVNULL, text=True, capture_output=True)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def test_help_needs_no_python_or_mutations(self):
        result = self.run_install('--help')
        self.assertEqual(result.returncode, 0)
        self.assertIn('--runtime-only', result.stdout)
        self.assertEqual(self.calls(), [])

    def test_automated_selection_required_before_external_calls(self):
        result = self.run_install('--user', 'alice', '--yes')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Choose --agent', result.stderr)
        self.assertEqual(self.calls(), [])

    def test_agent_validation_precedes_apt_and_install(self):
        result = self.run_install('--prefix', self.prefix, '--user', 'alice', '--agent', 'codex', '--yes')
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls()
        validation = next(i for i,c in enumerate(calls) if '--validate-only' in c)
        apt = next(i for i,c in enumerate(calls) if c[0] == 'apt-get')
        install = next(i for i,c in enumerate(calls) if 'install' in c)
        self.assertLess(validation, apt)
        self.assertLess(apt, install)
        packages = next(c for c in calls if c[:2] == ['apt-get', 'install'])
        self.assertIn('at-spi2-core', packages)
        self.assertIn('dbus-x11', packages)
        self.assertEqual(calls[-1], ['python', '-m', 'luda.setup', '--prefix', str(self.prefix),
                                    '--user', 'alice', '--agent', 'codex', '--yes'])

    def test_rejected_setup_cannot_install_runtime_or_dependencies(self):
        result = self.run_install('--prefix', self.prefix, '--user', 'alice', '--agent', 'unknown', reject=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(c[0] == 'apt-get' or 'install' in c for c in self.calls()))

    def test_multiple_agents_and_project_forwarded_verbatim(self):
        project = self.directory / 'project with spaces'
        result = self.run_install('--prefix', self.prefix, '--user', 'alice', '--skip-system',
                                  '--agent', 'codex', '--agent', 'claude-code', '--scope', 'project', '--project', project)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(str(project), self.calls()[-1])
        self.assertEqual(self.calls()[-1].count('--agent'), 2)
        self.assertFalse(any(c[0] == 'apt-get' for c in self.calls()))

    def test_runtime_image_does_not_run_setup_or_doctor(self):
        result = self.run_install('--prefix', self.prefix, '--user', 'alice', '--runtime-only', '--skip-system', '--yes')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('No agents were configured', result.stdout)
        self.assertFalse(any('luda.setup' in c or 'doctor' in c for c in self.calls()))

    def test_legacy_positional_install_remains_runtime_only(self):
        result = self.run_install(self.prefix, '--skip-system', '--user', 'alice')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertFalse(any('luda.setup' in c for c in self.calls()))

    def test_legacy_positional_can_opt_into_setup(self):
        result = self.run_install(self.prefix, '--skip-system', '--user', 'alice', '--agent', 'codex')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.calls()[-1][0], 'python')

    def test_root_must_explicitly_select_account(self):
        result = self.run_install('--runtime-only', '--skip-system')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('Specify --user', result.stderr)
        self.assertFalse(any('install' in c for c in self.calls()))

    def test_custom_export_can_replace_agent_selection(self):
        result = self.run_install('--prefix', self.prefix, '--user', 'alice', '--skip-system', '--export', '/tmp/bundle')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--export', self.calls()[-1])

    def test_invalid_combinations_refused(self):
        for options in [('--runtime-only', '--agent', 'codex'), ('--prefix', '/opt/a', '--prefix', '/opt/b'),
                        ('--agent',), ('--surprise',), ('--user', 'alice', '--user', 'bob')]:
            with self.subTest(options=options):
                result = self.run_install(*options)
                self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.calls(), [])

    def test_runtime_only_scope_refused_before_apt(self):
        result = self.run_install('--prefix', self.prefix, '--runtime-only', '--user', 'alice', '--scope', 'project')
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(c[0] == 'apt-get' or 'install' in c for c in self.calls()))


if __name__ == '__main__':
    unittest.main()
