"""Owned process and root-directory cleanup must be proved, never inferred."""
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
from luda.browser import OwnedBrowser
from luda.common import DesktopError
from luda._browser_guard import clear_profile


class BrowserCleanupTests(unittest.TestCase):
    def test_profile_root_replacement_preserves_other_directory(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);profile=root/'profile';profile.mkdir()
            (profile/'owned').write_text('owned')
            fd=os.open(profile,os.O_RDONLY|os.O_DIRECTORY)
            identity=(os.fstat(fd).st_dev,os.fstat(fd).st_ino)
            profile.rename(root/'original');profile.mkdir();(profile/'keep').write_text('unrelated')
            try:self.assertFalse(clear_profile(profile,fd,identity))
            finally:os.close(fd)
            self.assertEqual((profile/'keep').read_text(),'unrelated')
            self.assertEqual(list((root/'original').iterdir()),[])

    def test_profile_symlink_does_not_follow_external_files(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);profile=root/'profile';profile.mkdir();other=root/'other';other.mkdir()
            (other/'keep').write_text('keep');(profile/'link').symlink_to(other,target_is_directory=True)
            fd=os.open(profile,os.O_RDONLY|os.O_DIRECTORY);info=os.fstat(fd)
            try:self.assertTrue(clear_profile(profile,fd,(info.st_dev,info.st_ino)))
            finally:os.close(fd)
            self.assertEqual((other/'keep').read_text(),'keep')

    def test_stopped_guardian_resumes_and_proves_owned_cleanup(self):
        with tempfile.TemporaryDirectory() as root:
            root=Path(root);package=root/'luda';package.mkdir();(package/'__init__.py').touch()
            (package/'_browser_worker.py').write_text("import os,time,tempfile\nfrom pathlib import Path\nt=Path(tempfile.mkdtemp()) / 'download'; t.write_text('synthetic')\nPath(os.environ['PROBE_TMP']).write_text(str(t))\nPath(os.environ['PROBE_PID']).write_text(str(os.getpid()))\ntime.sleep(60)\n")
            proof,write=os.pipe2(os.O_CLOEXEC|os.O_NONBLOCK)
            guard=Path(__file__).resolve().parents[1]/'src/luda/_browser_guard.py'
            process=subprocess.Popen([sys.executable,str(guard),str(root),str(write)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,pass_fds=(write,),env=dict(os.environ,PYTHONPATH=str(root),PROBE_PID=str(root/'pid'),PROBE_TMP=str(root/'temporary')))
            os.close(write);owner=OwnedBrowser(None);owner.process=process;owner.cleanup_proof=proof
            try:
                end=time.monotonic()+3
                while not (root/'pid').exists() and time.monotonic()<end:time.sleep(.01)
                download=Path((root/'temporary').read_text());self.assertEqual(download.read_text(),'synthetic')
                self.assertTrue(download.is_relative_to(next(root.glob('owned-browser-*'))))
                worker=int((root/'pid').read_text());os.kill(process.pid,signal.SIGSTOP)
                owner.close()
                self.assertIsNone(owner.process)
                self.assertFalse(Path('/proc',str(worker)).exists())
                self.assertEqual(list(root.glob('owned-browser-*')),[])
                self.assertFalse(download.exists())
            finally:
                if process.poll() is None:os.kill(process.pid,signal.SIGCONT);process.terminate();process.wait(timeout=4)
                for stream in (process.stdin,process.stdout):stream.close()

    def test_missing_cleanup_proof_remains_unconfirmed(self):
        process=subprocess.Popen([sys.executable,'-c','pass'],stdin=subprocess.PIPE,stdout=subprocess.PIPE)
        process.wait(timeout=3);owner=OwnedBrowser(None);owner.process=process
        with self.assertRaises(DesktopError) as caught:owner.close()
        self.assertEqual(caught.exception.code,'BROWSER_CLEANUP_UNCONFIRMED')
        self.assertIs(owner.process,process)
