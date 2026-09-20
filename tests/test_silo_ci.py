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
