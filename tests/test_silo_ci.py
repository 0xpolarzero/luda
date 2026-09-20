import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('runner', ROOT/'tests/tools/silo-registration/run.py')
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class SiloCiTests(unittest.TestCase):
    def test_native_evidence_requires_actual_cases_and_no_skips(self):
        names = ['actual_cli_registration_and_removal_reconcile_without_replay',
                 'actual_cli_recovery_repairs_only_proven_source_and_receipt_without_install_replay',
                 'actual_cli_reviewed_update_preserves_other_vm_and_records_uncertainty',
                 'actual_cli_failed_removal_is_not_replayed',
                 'actual_cli_two_vm_configuration_and_idempotency']
        text = '\n'.join('test codex_desktop::tests::'+name+' ... ok' for name in names)
        text += '\ntest result: ok. 10 passed; 0 failed; 0 ignored;'
        self.assertTrue(runner.native_complete(text))
        self.assertFalse(runner.native_complete(text.replace(names[0], 'unrelated')))
        self.assertFalse(runner.native_complete(text.replace('0 ignored', '1 ignored')))
        self.assertFalse(runner.native_complete(text.replace(' ... ok', ' ... ignored', 1)))

    def test_executes_upstream_sources_and_explicit_ignored_cases(self):
        commands = dict(runner.commands(Path('/tmp/source with spaces')))
        self.assertIn('/tmp/source with spaces/app/SiloUI/src-tauri/Cargo.toml', commands['native'])
        self.assertIn('--locked', commands['native'])
        self.assertIn('--include-ignored', commands['native'])
        self.assertIn('src/desktop/codex-desktop-registration.test.tsx', commands['frontend'])

    def test_browser_native_requires_exact_case_and_count(self):
        text='test desktop::tests::browser_actions_are_fixed_and_status_is_strict ... ok\ntest result: ok. 1 passed; 0 failed; 0 ignored;'
        self.assertTrue(runner.browser_action_complete(text))
        self.assertFalse(runner.browser_action_complete(text.replace('1 passed','0 passed')))
        self.assertFalse(runner.browser_action_complete(text.replace('is_strict','unrelated')))
        self.assertFalse(runner.browser_action_complete(text.replace('0 ignored','1 ignored')))
        self.assertIn('--exact',dict(runner.commands(Path('/tmp/silo')))['browser-action-native'])

    def test_frontend_requires_new_browser_cases_and_no_skips(self):
        text='Test Files  3 passed (3)\nTests  34 passed (34)'
        self.assertTrue(runner.frontend_complete(text))
        self.assertTrue(runner.frontend_complete('\x1b[32m'+text+'\x1b[0m'))
        self.assertFalse(runner.frontend_complete(text.replace('34','30')))
        self.assertFalse(runner.frontend_complete(text.replace('34 passed (34)','33 passed | 1 skipped (34)')))
