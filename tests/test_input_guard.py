import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from luda.common import DesktopError
from luda.input_guard import held_button

class InputGuardTests(unittest.TestCase):
    def test_invalid_button_never_spawns(self):
        with patch('luda.input_guard.subprocess.Popen') as spawn:
            with self.assertRaises(DesktopError):
                with held_button('9'):pass
        spawn.assert_not_called()
    def test_normal_release_disarms_guard(self):
        with patch('luda.input_guard.run') as run:
            with held_button('1'):pass
        self.assertEqual([c.args[0] for c in run.call_args_list],[['xdotool','mousedown','1'],['xdotool','mouseup','1']])
    def test_original_error_preserved_and_release_attempted(self):
        with patch('luda.input_guard.run') as run:
            with self.assertRaises(DesktopError) as caught:
                with held_button('1'):raise DesktopError('CANCELLED','test',effect='uncertain')
        self.assertEqual(caught.exception.code,'CANCELLED')
        self.assertTrue(run.call_args.kwargs['cleanup'])
    def test_release_failure_preserves_original_error_and_companion_retries(self):
        with tempfile.TemporaryDirectory() as directory:
            proof=Path(directory)/'released'
            executable=Path(directory)/'xdotool'
            executable.write_text('#!'+sys.executable+'\nfrom pathlib import Path\nPath('+repr(str(proof))+').touch()\n')
            executable.chmod(0o700)
            with patch.dict(os.environ,PATH=directory),patch('luda.input_guard.run',side_effect=[b'',DesktopError('BACKEND_ERROR','release failed')]):
                with self.assertRaises(DesktopError) as caught:
                    with held_button('1'):raise DesktopError('CANCELLED','original',effect='uncertain')
            self.assertEqual(caught.exception.code,'CANCELLED')
            self.assertEqual(caught.exception.details['button_release_failed'],'BACKEND_ERROR')
            self.assertTrue(proof.exists())

    def test_parent_death_runs_independent_release_command(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory);proof=path/'released'
            executable=path/'xdotool'
            executable.write_text('#!'+sys.executable+'\nimport pathlib,sys\npathlib.Path('+repr(str(proof))+').write_text(" ".join(sys.argv[1:]))\n')
            executable.chmod(0o700)
            reader,writer=os.pipe()
            guard=subprocess.Popen([sys.executable,'-m','luda._input_guard',str(reader),'2'],pass_fds=(reader,),env=dict(os.environ,PATH=directory),stdout=subprocess.PIPE)
            os.close(reader)
            try:
                self.assertEqual(guard.stdout.read(1),b'R')
                os.write(writer,b'A')
                os.close(writer);writer=None
                self.assertEqual(guard.wait(timeout=3),0)
                self.assertEqual(proof.read_text(),'mouseup 2')
            finally:
                if writer is not None:os.close(writer)
                guard.stdout.close()
                if guard.poll() is None:guard.kill();guard.wait()

if __name__=='__main__':unittest.main()
