"""Deterministic syscall failures; these tests do not fill a real filesystem."""
import errno
import os
from pathlib import Path
import tempfile
import subprocess
import sys
import unittest
from unittest.mock import Mock, patch

from PIL import Image
from luda.common import DesktopError
from luda.desktop import Desktop


class StorageFaults(unittest.TestCase):
    def driver(self):
        d = Desktop()
        self.addCleanup(d.close)
        d.x = Mock()
        d.x.root = 1
        d.x.geometry.return_value = {'width': 100, 'height': 100}
        d.x.topology.return_value={'root':d.x.geometry.return_value,'randr':{'version':[1,6],'monitors':[],'crtcs':[]}}
        d.list_windows = Mock(return_value=[])
        d.observe_popups = Mock(return_value=[])
        d.target_window = Mock(return_value={'wm_class': [], 'window_id': 'fixture'})
        d.key = Mock()
        return d

    def test_startup_storage_diagnostic_does_not_leak_filename(self):
        for number in (errno.ENOSPC, errno.EDQUOT, errno.EROFS, errno.EACCES):
            with self.subTest(number=number), patch('luda.desktop.Path.mkdir', side_effect=OSError(number, 'private payload', '/secret/location')):
                with self.assertRaises(DesktopError) as caught:
                    Desktop()
                self.assertEqual(caught.exception.code, 'STORAGE_UNAVAILABLE')
                self.assertNotIn('secret', str(caught.exception))
                self.assertNotIn('private', str(caught.exception))

    def test_startup_admission_failure_closes_lock_descriptor(self):
        before = len(list(Path('/proc/self/fd').iterdir()))
        with patch('luda.desktop.Admission', side_effect=OSError(errno.EMFILE, 'private filename')):
            with self.assertRaises(DesktopError) as caught:
                Desktop()
        self.assertEqual(caught.exception.code, 'RESOURCE_UNAVAILABLE')
        self.assertEqual(len(list(Path('/proc/self/fd').iterdir())), before)

    def test_screenshot_creation_failure_returns_no_snapshot(self):
        d = self.driver()
        with patch('luda.desktop.tempfile.TemporaryDirectory', side_effect=OSError(errno.EROFS, 'private path')):
            with self.assertRaises(DesktopError) as caught:
                d.observe()
        self.assertEqual(caught.exception.code, 'STORAGE_UNAVAILABLE')
        self.assertEqual(caught.exception.effect, 'none')
        self.assertFalse(d.snapshots)

    def test_capture_write_failure_cleans_owned_directory(self):
        d = self.driver()
        with tempfile.TemporaryDirectory() as root:
            d.runtime = Path(root)
            with patch('luda.desktop.run', side_effect=OSError(errno.ENOSPC, 'capture write')):
                with self.assertRaises(DesktopError) as caught:
                    d.observe()
            self.assertEqual(caught.exception.code, 'STORAGE_UNAVAILABLE')
            self.assertEqual(list(Path(root).iterdir()), [])
            self.assertFalse(d.snapshots)

    def test_preparing_clipboard_failure_preserves_existing_owner(self):
        d = self.driver()
        d.clipboard_owner = Mock()
        with patch('luda.desktop.tempfile.NamedTemporaryFile', side_effect=OSError(errno.ENOSPC, 'private payload')), patch('luda.desktop.stop_process') as stop:
            with self.assertRaises(DesktopError) as caught:
                d.paste('fixture', 'secret')
            self.assertEqual(caught.exception.code, 'STORAGE_UNAVAILABLE')
            stop.assert_not_called()
            d.key.assert_not_called()
        d.clipboard_owner = None

    def test_clipboard_spawn_resource_failure_is_uncertain_and_cleans_payload(self):
        d = self.driver()
        with tempfile.TemporaryDirectory() as root:
            d.runtime = Path(root)
            with patch('luda.desktop.subprocess.Popen', side_effect=OSError(errno.EMFILE, 'private payload')):
                with self.assertRaises(DesktopError) as caught:
                    d.paste('fixture', 'secret')
            self.assertEqual(caught.exception.code, 'RESOURCE_UNAVAILABLE')
            self.assertEqual(caught.exception.effect, 'uncertain')
            self.assertEqual(list(Path(root).iterdir()), [])
            d.key.assert_not_called()

    def test_missing_clipboard_executable_is_not_a_storage_error(self):
        d = self.driver()
        with patch('luda.desktop.subprocess.Popen', side_effect=FileNotFoundError(errno.ENOENT, 'missing')):
            with self.assertRaises(DesktopError) as caught:
                d.paste('fixture', 'payload')
        self.assertEqual(caught.exception.code, 'DEPENDENCY_MISSING')
        d.key.assert_not_called()

    def test_real_descriptor_exhaustion_in_private_child(self):
        code = r"""
import os,resource,tempfile
from pathlib import Path
from luda.desktop import Desktop
from luda.common import DesktopError
with tempfile.TemporaryDirectory() as directory:
 d=Desktop();d.runtime=Path(directory);d.target_window=lambda *args,**kwargs:{'wm_class':[]}
 d.key=lambda *args,**kwargs: (_ for _ in ()).throw(AssertionError('key dispatched'))
 prior=resource.getrlimit(resource.RLIMIT_NOFILE)
 for spare in (0,1):
  descriptors=[]
  try:
   resource.setrlimit(resource.RLIMIT_NOFILE,(min(48,prior[0]),prior[1]))
   while True:
    try:descriptors.append(os.open('/dev/null',os.O_RDONLY))
    except OSError:break
   if spare:os.close(descriptors.pop())
   try:d.paste('fixture','private payload')
   except DesktopError as exc:assert exc.code=='RESOURCE_UNAVAILABLE',exc.code
   else:raise AssertionError('exhausted process accepted clipboard operation')
  finally:
   for fd in descriptors:os.close(fd)
   resource.setrlimit(resource.RLIMIT_NOFILE,prior)
  assert list(Path(directory).iterdir())==[]
 d.close()
print('both descriptor and subprocess-pipe exhaustion diagnosed')
"""
        result = subprocess.run([sys.executable, '-c', code], capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('both descriptor and subprocess-pipe', result.stdout)


if __name__ == '__main__':
    unittest.main()
