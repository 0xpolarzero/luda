"""Adversarial contracts without a display; no test mutates a user application."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import Mock, patch

from luda.common import DesktopError, process_identity
from luda.desktop import Desktop


class IsolatedDesktop(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.runtime = patch('luda.desktop.tempfile.gettempdir', return_value=self.folder.name)
        self.runtime.start()
        self.addCleanup(self.runtime.stop)
        self.desktop = Desktop()
        self.addCleanup(self.desktop.close)


class Coordination(IsolatedDesktop):
    def test_same_thread_reentry_refused_then_lock_recovers(self):
        with self.desktop.transaction():
            with self.assertRaises(DesktopError) as raised:
                with self.desktop.transaction():
                    self.fail('Reentry acquired the lock')
            self.assertEqual(raised.exception.code, 'BUSY')
        with self.desktop.transaction():
            pass

    def test_other_thread_refused_before_body(self):
        observed = []
        def contender():
            try:
                with self.desktop.transaction():
                    observed.append('entered')
            except DesktopError as exc:
                observed.append(exc.code)
        with self.desktop.transaction():
            thread = threading.Thread(target=contender)
            thread.start()
            thread.join(1)
            self.assertFalse(thread.is_alive())
        self.assertEqual(observed, ['BUSY'])

    def test_exception_releases_both_locks(self):
        other = Desktop()
        self.addCleanup(other.close)
        with self.assertRaisesRegex(RuntimeError, 'fixture'):
            with self.desktop.transaction():
                raise RuntimeError('fixture')
        with other.transaction():
            pass
        with self.desktop.transaction():
            pass

    def test_other_instance_refused_and_recovers(self):
        other = Desktop()
        self.addCleanup(other.close)
        with self.desktop.transaction():
            with self.assertRaises(DesktopError) as raised:
                with other.transaction():
                    self.fail('Competing instance entered')
            self.assertEqual(raised.exception.code, 'BUSY')
        with other.transaction():
            pass

    def test_independent_displays_do_not_contend(self):
        with patch.dict(os.environ, {'DISPLAY': ':qualification-other'}):
            other = Desktop()
        self.addCleanup(other.close)
        with self.desktop.transaction(), other.transaction():
            pass

    def test_crashed_process_releases_file_lock(self):
        program = '''import fcntl, os, sys, time
fd = os.open(sys.argv[1], os.O_RDWR)
fcntl.flock(fd, fcntl.LOCK_EX)
print('locked', flush=True)
time.sleep(30)
'''
        path = os.readlink(f'/proc/self/fd/{self.desktop.lockfd}')
        child = subprocess.Popen([sys.executable, '-c', program, path], stdout=subprocess.PIPE, text=True)
        try:
            self.assertEqual(child.stdout.readline().strip(), 'locked')
            with self.assertRaises(DesktopError):
                with self.desktop.transaction():
                    self.fail('Crash fixture lock ignored')
            child.kill()
            child.wait(timeout=2)
            with self.desktop.transaction():
                pass
        finally:
            if child.poll() is None:
                child.kill()
                child.wait(timeout=2)
            child.stdout.close()


class HandleIntegrity(IsolatedDesktop):
    def test_unknown_element_never_calls_accessibility(self):
        with patch.object(self.desktop, 'ax') as ax:
            with self.assertRaises(DesktopError) as raised:
                self.desktop.element('foreign-server-handle', 'invoke', action='click')
        self.assertEqual(raised.exception.code, 'STALE_TARGET')
        ax.assert_not_called()

    def test_expired_element_never_resolves_window(self):
        self.desktop.elements['old'] = {'time': time.monotonic() - 61}
        with patch.object(self.desktop, 'target_window') as target:
            with self.assertRaises(DesktopError) as raised:
                self.desktop.element('old', 'set', text='must not enter')
        self.assertEqual(raised.exception.code, 'STALE_TARGET')
        target.assert_not_called()

    def test_process_reuse_rejected_before_accessibility(self):
        self.desktop.elements['element'] = {'time': time.monotonic(), 'window_id': 'w', 'node': {'start': 'old'}}
        with patch.object(self.desktop, 'target_window', return_value={'start': 'new'}), patch.object(self.desktop, 'ax') as ax:
            with self.assertRaises(DesktopError) as raised:
                self.desktop.element('element', 'invoke', action='click')
        self.assertEqual(raised.exception.code, 'STALE_TARGET')
        ax.assert_not_called()

    def test_expired_screenshot_never_resolves_target(self):
        self.desktop.snapshots['old'] = {'time': time.monotonic() - 16}
        with patch.object(self.desktop, 'target_window') as target:
            with self.assertRaises(DesktopError) as raised:
                self.desktop.point('w', 'old', 1, 1)
        self.assertEqual(raised.exception.code, 'STALE_OBSERVATION')
        target.assert_not_called()

    def test_missing_process_is_stale(self):
        with self.assertRaises(DesktopError) as raised:
            process_identity(2**31 - 1)
        self.assertEqual(raised.exception.code, 'STALE_TARGET')


class NoInputOnInvalidRequest(IsolatedDesktop):
    def test_bad_chords_send_no_command(self):
        with patch.object(self.desktop, 'target_window'), patch('luda.desktop.run') as run:
            for chord in ['ctrl+Return\n', 'ctrl++a', 'alt+$(id)', 'Return;id', 'shift+', '', 'ctrl+F25']:
                with self.subTest(chord=chord), self.assertRaises(DesktopError):
                    self.desktop.key('w', chord)
            run.assert_not_called()

    def test_invalid_clipboard_shortcut_never_starts_owner(self):
        with patch.object(self.desktop, 'target_window'), patch('luda.desktop.subprocess.Popen') as popen:
            with self.assertRaises(DesktopError):
                self.desktop.paste('w', 'literal', 'guess')
            popen.assert_not_called()

    def test_empty_paste_does_not_replace_clipboard(self):
        with patch.object(self.desktop, 'target_window'), patch('luda.desktop.subprocess.Popen') as popen:
            result = self.desktop.paste('w', '', 'ctrl_v')
            self.assertEqual(result['effect'], 'none')
            popen.assert_not_called()

    def test_invalid_text_does_not_even_resolve_window(self):
        with patch.object(self.desktop, 'target_window') as target:
            with self.assertRaises(DesktopError):
                self.desktop.paste('w', 'a\x00b', 'ctrl_v')
            target.assert_not_called()


if __name__ == '__main__':
    unittest.main()
