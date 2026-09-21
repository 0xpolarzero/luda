"""Live evaluator isolation guards; no evaluated model or desktop is launched."""
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('skill_live', ROOT / 'scripts/evaluation/skill_live.py')
live = importlib.util.module_from_spec(spec)
spec.loader.exec_module(live)


class LiveGuards(unittest.TestCase):
    def environment(self, display=':98'):
        return {'HOME': '/tmp/private/home', 'DISPLAY': display,
                'LUDA_ISOLATED_TEST_DISPLAY': '1', 'LUDA_MATRIX_PROCESS_TOKEN': 'owned',
                'XDG_CONFIG_HOME': '/tmp/private/config'}

    def test_private_ordinary_session_allowed(self):
        with patch.dict(os.environ, self.environment(), clear=True), patch.object(os, 'geteuid', return_value=1000):
            live.check_child(Path('/tmp/private'))

    def test_shared_display_and_root_rejected(self):
        for display, uid in ((':1', 1000), (':1.0', 1000), ('', 1000), (':98', 0)):
            with self.subTest(display=display, uid=uid):
                with patch.dict(os.environ, self.environment(display), clear=True), patch.object(os, 'geteuid', return_value=uid):
                    with self.assertRaises(RuntimeError):
                        live.check_child(Path('/tmp/private'))

    def test_inherited_profile_and_missing_ownership_rejected(self):
        for override in ({'HOME': '/home/ubuntu'}, {'XDG_CONFIG_HOME': '/home/ubuntu/.config'}, {'LUDA_MATRIX_PROCESS_TOKEN': ''}):
            with patch.dict(os.environ, dict(self.environment(), **override), clear=True), patch.object(os, 'geteuid', return_value=1000):
                with self.assertRaises(RuntimeError):
                    live.check_child(Path('/tmp/private'))

    def test_changed_entry_cannot_run_under_old_acceptance(self):
        with tempfile.TemporaryDirectory() as directory:
            skill = Path(directory)
            (skill / 'references').mkdir()
            for name in live.REFERENCES:
                (skill / 'references' / name).write_text('reference')
            (skill / 'SKILL.md').write_text('changed skill')
            with self.assertRaisesRegex(ValueError, 'accepted artifact'):
                live.checked_skill(skill)

    def test_timeout_and_exited_launcher_are_failures(self):
        process = unittest.mock.Mock()
        process.poll.return_value = 1
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, 'ready.json'):
                live.wait_for(Path(directory) / 'ready.json', process, .01)
            process.poll.return_value = None
            with self.assertRaisesRegex(RuntimeError, 'ready.json'):
                live.wait_for(Path(directory) / 'ready.json', process, 0)


if __name__ == '__main__':
    unittest.main()
