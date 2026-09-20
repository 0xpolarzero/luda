"""Qualification isolation and cleanup faults, independent of GUI outcomes."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from unittest.mock import patch
SCRIPTS=Path(__file__).resolve().parents[1]/'scripts';sys.path.insert(0,str(SCRIPTS))
spec=importlib.util.spec_from_file_location('qualification_matrix',SCRIPTS/'qualification_matrix.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class Matrix(unittest.TestCase):
    def test_known_failures_still_nonzero(self):
        token=uuid.uuid4().hex
        with tempfile.TemporaryFile() as log:
            result=m.run_bounded([sys.executable,'-c','raise SystemExit(7)'],dict(os.environ,**{m.TOKEN_KEY:token}),log,2,token)
        self.assertEqual(result['status'],'failed');self.assertEqual(result['returncode'],7)
    def test_fresh_environment_detaches_all_inherited_sessions(self):
        with tempfile.TemporaryDirectory() as temp,patch.dict(os.environ,{'DISPLAY':':1','AT_SPI_BUS_ADDRESS':'old','GTK_IM_MODULE':'ibus','SESSION_MANAGER':'old'}):
            env=m.private_environment(Path(temp),'unique')
            for key in ('DISPLAY','AT_SPI_BUS_ADDRESS','GTK_IM_MODULE','SESSION_MANAGER'):self.assertNotIn(key,env)
            for key in ('XDG_CONFIG_HOME','XDG_DATA_HOME','XDG_CACHE_HOME','XDG_RUNTIME_DIR'):
                self.assertEqual(Path(env[key]).stat().st_mode&0o777,0o700)
            self.assertEqual(env['HOME'],os.environ['HOME'])
    def test_detached_descendant_cleaned_after_launcher_exits(self):self.descendant('',2,'passed')
    def test_detached_descendant_cleaned_on_timeout(self):self.descendant('import time;time.sleep(30)',.1,'timeout')
    def descendant(self,tail,timeout,status):
        with tempfile.TemporaryDirectory() as temp,tempfile.TemporaryFile() as log:
            late=Path(temp)/'late';token=uuid.uuid4().hex
            child="import time;from pathlib import Path;time.sleep(.8);Path(%r).write_text('effect')"%str(late)
            code='import subprocess,sys;subprocess.Popen([sys.executable,"-c",%r],start_new_session=True);%s'%(child,tail)
            result=m.run_bounded([sys.executable,'-c',code],dict(os.environ,**{m.TOKEN_KEY:token}),log,timeout,token)
            self.assertEqual(result['status'],status);self.assertEqual(result['cleanup']['survivors'],[])
            time.sleep(.9);self.assertFalse(late.exists())
    def test_cleanup_does_not_touch_other_invocation(self):
        token=uuid.uuid4().hex
        p=subprocess.Popen([sys.executable,'-c','import time;time.sleep(30)'],env=dict(os.environ,**{m.TOKEN_KEY:token}),start_new_session=True)
        try:
            m.cleanup_owned('different-'+token);self.assertIsNone(p.poll())
        finally:m.stop(p)
    def test_all_related_ids_are_real_and_no_agent_eval(self):
        catalog=json.loads((m.ROOT/'docs/requirements.json').read_text())
        ids={c['id'] for f in catalog['features'] for c in f['cases']}
        for suite in m.SUITES.values():
            self.assertTrue(set(suite['related_requirements'])<=ids)
            self.assertTrue((m.ROOT/'tests'/suite['script']).is_file())
            self.assertNotIn('agent',suite['script'])
    def test_owned_window_managers_are_not_started_twice(self):
        for name in ('data-controls','firefox','ime','ime-browser','accessibility-lifecycle','mcp-reconnect','x11-isolation','window-tokens','window-metadata-capacity'):
            self.assertFalse(m.SUITES[name]['runner_window_manager'])
    def test_missing_browser_is_explicit(self):
        with patch.object(m.shutil,'which',return_value='/bin/true'),patch.object(m.subprocess,'run',return_value=type('R',(),{'returncode':0})()):
            self.assertFalse(m.dependencies(m.SUITES['browser'],None)['browser_executable'])
    def test_electron_dependency_is_separate_from_browser(self):
        with patch.object(m.shutil,'which',return_value='/bin/true'),patch.object(m.subprocess,'run',return_value=type('R',(),{'returncode':0})()):
            checks=m.dependencies(m.SUITES['electron'],'/bin/true',None)
            self.assertFalse(checks['electron_executable'])
            self.assertNotIn('browser_executable',checks)
            self.assertTrue(m.dependencies(m.SUITES['electron'],None,'/bin/true')['electron_executable'])
    def test_firefox_dependency_is_separate_and_flag_reaches_fixture(self):
        with patch.object(m.shutil,'which',return_value='/bin/true'),patch.object(m.subprocess,'run',return_value=type('R',(),{'returncode':0})()):
            checks=m.dependencies(m.SUITES['firefox'],'/bin/true','/bin/true')
            self.assertFalse(checks['firefox_executable']);self.assertNotIn('browser_executable',checks)
            self.assertTrue(m.dependencies(m.SUITES['firefox'],None,None,'/bin/true')['firefox_executable'])
        with patch.object(m.subprocess,'call',return_value=1) as run,patch.object(m.subprocess,'Popen') as wm:
            self.assertEqual(m.inside('firefox',None,None,'/test/firefox'),1)
            self.assertEqual(run.call_args.args[0][-2:],['--executable','/test/firefox'])
            wm.assert_not_called()
if __name__=='__main__':unittest.main()
