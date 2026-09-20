import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
from luda.common import DesktopError
from luda.input_guard import held_button

GENERATION='a'*32

def native(operation,*args,**kwargs):
    return {'server_generation':GENERATION} if operation=='generation' else {'released':True}


class InputGuardTests(unittest.TestCase):
    def test_invalid_button_never_spawns(self):
        with patch('luda.input_guard.subprocess.Popen') as spawn:
            with self.assertRaises(DesktopError):
                with held_button('9'):pass
        spawn.assert_not_called()
    def test_normal_release_disarms_guard(self):
        with patch('luda.input_guard._native_input',side_effect=native) as run:
            with held_button('1'):pass
        self.assertEqual([c.args[0] for c in run.call_args_list],['generation','press','release'])
        self.assertEqual(run.call_args.args,('release','1',GENERATION))
        self.assertTrue(run.call_args.kwargs['cleanup'])
    def test_original_error_preserved_and_release_attempted(self):
        with patch('luda.input_guard._native_input',side_effect=native) as run:
            with self.assertRaises(DesktopError) as caught:
                with held_button('1'):raise DesktopError('CANCELLED','test',effect='uncertain')
        self.assertEqual(caught.exception.code,'CANCELLED')
        self.assertTrue(run.call_args.kwargs['cleanup'])
    def test_replacement_server_cleanup_reports_skip(self):
        with patch('luda.input_guard._native_input',side_effect=[{'server_generation':GENERATION},{'pressed':True},{'session_changed':True,'cleanup_skipped':True}]):
            with self.assertRaises(DesktopError) as caught:
                with held_button('1'):pass
        self.assertEqual(caught.exception.code,'SESSION_CHANGED')
        self.assertTrue(caught.exception.details['cleanup_skipped'])
    def test_parent_death_uses_original_generation(self):
        with tempfile.TemporaryDirectory() as directory:
            proof=Path(directory)/'released'
            script='''import json,sys
from pathlib import Path
from types import SimpleNamespace
from luda import _input_guard as guard
def release(*args,**kwargs):
 Path(sys.argv[4]).write_bytes(kwargs['input'])
 return SimpleNamespace(returncode=0,stdout=b'{"released":true}')
guard.subprocess.run=release
raise SystemExit(guard.main())
'''
            reader,writer=os.pipe()
            guard=subprocess.Popen([sys.executable,'-c',script,str(reader),'2',GENERATION,str(proof)],pass_fds=(reader,),stdout=subprocess.PIPE)
            os.close(reader)
            try:
                self.assertEqual(guard.stdout.read(1),b'R')
                os.write(writer,b'A');os.close(writer);writer=None
                self.assertEqual(guard.wait(timeout=3),0)
                self.assertEqual(json.loads(proof.read_bytes()),{'operation':'release','button':'2','server_generation':GENERATION})
            finally:
                if writer is not None:os.close(writer)
                guard.stdout.close()
                if guard.poll() is None:guard.kill();guard.wait()


if __name__=='__main__':unittest.main()
