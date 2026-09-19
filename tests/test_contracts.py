import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from luda.common import DesktopError, run, validate_text
from luda.desktop import Desktop


class Contracts(unittest.TestCase):
    def test_exact_unicode_whitespace_accepted(self):
        value='\t alpha\n\n日本語 e\u0301 👩🏽\u200d💻 العربية  \n'
        validate_text(value)
        self.assertEqual(value.encode().decode(),value)

    def test_control_and_invalid_unicode_rejected_before_input(self):
        for value in ['a\0b','x\r\ny','\x1b[31m','x\x7f','\ud800']:
            with self.subTest(value=repr(value)):
                with self.assertRaises(DesktopError) as ctx:validate_text(value)
                self.assertEqual(ctx.exception.code,'UNSUPPORTED_TEXT')
                self.assertEqual(ctx.exception.effect,'none')

    def test_utf8_byte_limit(self):
        validate_text('é'*500_000)
        with self.assertRaises(DesktopError) as ctx:validate_text('é'*500_001)
        self.assertEqual(ctx.exception.code,'TEXT_TOO_LARGE')

    def test_shell_metacharacters_remain_arguments(self):
        with tempfile.TemporaryDirectory() as folder:
            sentinel=Path(folder)/'must-not-exist'
            value=f'$(touch {sentinel}) `touch {sentinel}` ; "hello"\n'
            actual=run([sys.executable,'-c','import sys;sys.stdout.write(sys.argv[1])',value])
            self.assertEqual(actual.decode(),value)
            self.assertFalse(sentinel.exists())

    def test_timeout_preserves_uncertain_effect(self):
        began=time.monotonic()
        with self.assertRaises(DesktopError) as ctx:
            run([sys.executable,'-c','import time;time.sleep(10)'],timeout=.05,effect='uncertain')
        self.assertEqual(ctx.exception.code,'TIMEOUT')
        self.assertEqual(ctx.exception.effect,'uncertain')
        self.assertLess(time.monotonic()-began,1)

    def test_missing_program_is_actionable(self):
        with self.assertRaises(DesktopError) as ctx:run(['/no-such-silo-program'])
        self.assertEqual(ctx.exception.code,'DEPENDENCY_MISSING')

    def test_symlink_runtime_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/'target';target.mkdir()
            (Path(folder)/f'silo-desktop-{os.getuid()}').symlink_to(target,target_is_directory=True)
            with patch('luda.desktop.tempfile.gettempdir',return_value=folder):
                with self.assertRaises(DesktopError) as ctx:Desktop()
            self.assertEqual(ctx.exception.code,'UNSAFE_RUNTIME')
            self.assertEqual(list(target.iterdir()),[])

    def test_world_readable_runtime_refused(self):
        with tempfile.TemporaryDirectory() as folder:
            target=Path(folder)/f'silo-desktop-{os.getuid()}';target.mkdir(mode=0o755)
            with patch('luda.desktop.tempfile.gettempdir',return_value=folder):
                with self.assertRaises(DesktopError) as ctx:Desktop()
            self.assertEqual(ctx.exception.code,'UNSAFE_RUNTIME')


if __name__=='__main__':unittest.main()
