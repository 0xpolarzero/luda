import importlib.util,json,os,shutil,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import private_directory_cleanup as cleanup
spec=importlib.util.spec_from_file_location('managed_probe_runner',ROOT/'tests/evidence/managed-browser/run.py')
runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)

class ManagedCleanup(unittest.TestCase):
 def test_probe_failure_and_cleanup_are_separately_retained(self):
  with tempfile.TemporaryDirectory() as temp:
   output=Path(temp)/'evidence';seen=[]
   class Child:
    pid=123456789
    def wait(self,timeout):return 7
   def launch(command,**kwargs):
    seen.append(Path(kwargs['cwd']))
    self.assertEqual(Path(kwargs['env']['XDG_RUNTIME_DIR']),seen[-1]/'runtime')
    self.assertTrue(seen[-1].name.startswith('ld-test-'))
    return Child()
   with patch.object(runner.os,'getuid',return_value=os.getuid() or 1001),patch.object(runner.os,'killpg'),patch.object(runner.subprocess,'Popen',side_effect=launch),patch.object(cleanup,'cleanup',return_value={'status':'removed','owned_portal_mounts_detached':0}):
    self.assertEqual(runner.main(['--output',str(output),'--prefix',temp]),7)
   proof=json.loads((output/'private-directory-cleanup.json').read_text())
   self.assertEqual(proof['fixture_status'],'failed');self.assertEqual(proof['returncode'],7)
   shutil.rmtree(seen[0])

 def test_cleanup_failure_remains_failure_and_keeps_passed_probe(self):
  with tempfile.TemporaryDirectory() as temp:
   output=Path(temp)/'evidence';seen=[]
   class Child:
    pid=123456789
    def wait(self,timeout):return 0
   def launch(command,**kwargs):seen.append(Path(kwargs['cwd']));return Child()
   with patch.object(runner.os,'getuid',return_value=os.getuid() or 1001),patch.object(runner.os,'killpg'),patch.object(runner.subprocess,'Popen',side_effect=launch),patch.object(cleanup,'cleanup',side_effect=RuntimeError('unconfirmed')):
    with self.assertRaisesRegex(RuntimeError,'unconfirmed'):runner.main(['--output',str(output),'--prefix',temp])
   proof=json.loads((output/'private-directory-cleanup.json').read_text())
   self.assertEqual(proof['fixture_status'],'passed')
   self.assertTrue(proof['private_directory_cleanup']['directory_retained'])
   self.assertTrue(seen[0].exists());shutil.rmtree(seen[0])
