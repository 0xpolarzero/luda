"""Guest bootstrap ordering, literal arguments and honest partial completion."""
import importlib.util
import json
import os
from pathlib import Path
import sys
import subprocess
import time
import pwd
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
spec = importlib.util.spec_from_file_location('bootstrap_guest', ROOT / 'scripts/bootstrap_guest.py')
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)


class GuestBootstrap(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'source literal $(never-run)'
        for name in ['scripts/install.sh', 'scripts/manage_install.py', 'requirements.lock', 'pyproject.toml', 'skills/luda/SKILL.md']:
            p = self.source / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text('fixture')
        self.prefix = self.root / 'prefix with spaces'
        self.output = self.root / 'fresh output'
        self.account = patch.object(b.pwd, 'getpwnam', return_value=SimpleNamespace(pw_uid=os.getuid() or 1001))
        identity = patch.object(b, 'release_identity', return_value='selected')
        identity.start()
        self.addCleanup(identity.stop)
        self.account.start()
        self.addCleanup(self.account.stop)

    def call(self, **kwargs):
        return b.bootstrap(self.source, self.prefix, self.output, 'desktop', **kwargs)

    def status(self, state='running'):
        return dict(installed=True, version='1', user='desktop', state=state)

    def test_invalid_paths_account_and_existing_output_fail_before_any_child(self):
        with patch.object(b, 'desktop_status') as status, patch.object(b, 'run_process') as run:
            self.output.mkdir()
            self.assertEqual(self.call()['stage'], 'validation')
            self.output.rmdir()
            self.assertEqual(b.bootstrap(self.source, Path('/'), self.output, 'desktop')['stage'], 'validation')
            self.assertEqual(b.bootstrap(self.source, self.prefix, self.output, 'bad name')['stage'], 'validation')
            status.assert_not_called()
            run.assert_not_called()

    def test_stopped_or_missing_status_does_not_install_or_reserve_output(self):
        with patch.object(b, 'run_process') as run:
            for value in ('stopped', 'starting', 'failed'):
                with patch.object(b, 'desktop_status', return_value=self.status(value)):
                    result = self.call()
                    self.assertFalse(result['installation_completed'])
                    self.assertEqual(result['desktop']['state'], value)
                    self.assertFalse(self.output.exists())
            with patch.object(b, 'desktop_status', side_effect=b.BootstrapError('Missing helper')):
                self.assertEqual(self.call()['stage'], 'desktop_preflight')
            run.assert_not_called()

    def test_literal_argv_and_order_no_global_settings_or_lifecycle_action(self):
        events = []
        def install(argv, **kwargs):
            events.append('install')
            self.assertEqual(argv, ['bash', self.source / 'scripts/install.sh', self.prefix, '--skip-system'])
            self.assertIs(kwargs['stdout'], sys.stderr)
            self.assertIs(kwargs['stderr'], sys.stderr)
            self.prefix.mkdir()
            (self.prefix / 'current').symlink_to('releases/selected')
            return 0
        def doctor(prefix, user):
            events.append('doctor')
            return {'ready': True, 'private': 'not-forwarded'}
        def config(prefix, output, user, **kwargs):
            events.append('config')
            self.assertEqual(kwargs, {'placement': 'remote'})
            self.assertEqual(output, self.output / 'config')
        with patch.object(b, 'desktop_status', return_value=self.status()), patch.object(b, 'run_process', side_effect=install), patch.object(b, 'doctor', side_effect=doctor), patch.object(b, 'config', side_effect=config):
            result = self.call(skip_system=True)
        self.assertEqual(events, ['install', 'doctor', 'config'])
        self.assertTrue(result['ok'])
        self.assertFalse(result['codex_settings_modified'])
        self.assertNotIn('not-forwarded', json.dumps(result))
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o700)

    def test_install_failure_prevents_doctor_and_config(self):
        with patch.object(b, 'desktop_status', return_value=self.status()), patch.object(b, 'run_process', return_value=1), patch.object(b, 'doctor') as doctor, patch.object(b, 'config') as config:
            result = self.call()
        self.assertEqual(result['stage'], 'installation')
        self.assertIsNone(result['installation_completed'])
        doctor.assert_not_called()
        config.assert_not_called()

    def test_readiness_and_config_failure_keep_selected_release_and_redact_errors(self):
        for stage in ('readiness', 'configuration'):
            with self.subTest(stage=stage):
                if self.output.exists():
                    self.output.rmdir()
                self.prefix.mkdir(exist_ok=True)
                current = self.prefix / 'current'
                if not current.is_symlink():
                    current.symlink_to('releases/selected')
                with patch.object(b, 'desktop_status', return_value=self.status()), patch.object(b, 'run_process', return_value=0), patch.object(b, 'doctor', side_effect=b.InstallError('SENSITIVE') if stage == 'readiness' else None, return_value={'ready': True}), patch.object(b, 'config', side_effect=OSError('SENSITIVE')):
                    result = self.call()
                self.assertEqual(result['stage'], stage)
                self.assertTrue(result['installation_completed'])
                self.assertFalse(result['ok'])
                self.assertEqual(current.readlink(), Path('releases/selected'))
                self.assertNotIn('SENSITIVE', json.dumps(result))
                self.assertIn('fresh output', result['error'])

    def test_all_path_overlaps_and_nonroot_apt_refused_before_child(self):
        with patch.object(b, 'desktop_status') as status, patch.object(b, 'run_process') as run:
            for prefix, output in ((self.source, self.output), (self.source/'install', self.output),
                                   (self.prefix, self.source/'output'), (self.prefix, self.prefix/'output')):
                result=b.bootstrap(self.source,prefix,output,'desktop')
                self.assertEqual(result['stage'],'validation')
                self.assertFalse(result['installation_completed'])
            with patch.object(b.os,'getuid',return_value=1001), patch.object(b,'validate',return_value=(self.source,self.prefix,self.output)):
                result=self.call()
                self.assertEqual(result['stage'],'validation')
                self.assertIn('requires root',result['reason'])
            status.assert_not_called();run.assert_not_called()

    def test_changed_selection_refused_before_doctor_or_config(self):
        self.prefix.mkdir();(self.prefix/'current').symlink_to('releases/unexpected')
        with patch.object(b,'desktop_status',return_value=self.status()),patch.object(b,'run_process',return_value=0),patch.object(b,'doctor') as doctor,patch.object(b,'config') as config:
            result=self.call()
        self.assertEqual(result['stage'],'release_validation')
        self.assertTrue(result['installation_completed'])
        doctor.assert_not_called();config.assert_not_called()
        self.assertEqual((self.prefix/'current').readlink(),Path('releases/unexpected'))

    def test_readiness_and_config_hold_installation_lock(self):
        self.prefix.mkdir();(self.prefix/'current').symlink_to('releases/selected')
        observed=[]
        def require_locked(*args,**kwargs):
            with self.assertRaises(b.InstallError):
                with b.locked(self.prefix):pass
            observed.append(True)
            return {'ready':True}
        with patch.object(b,'desktop_status',return_value=self.status()),patch.object(b,'run_process',return_value=0),patch.object(b,'doctor',side_effect=require_locked),patch.object(b,'config',side_effect=require_locked):
            self.assertTrue(self.call()['ok'])
        self.assertEqual(len(observed),2)

    def test_detached_child_timeout_has_no_late_effect(self):
        marker=self.root/'delayed-effect'
        pidfile=self.root/'child-pid'
        child_code='import os,time;from pathlib import Path;Path('+repr(str(pidfile))+').write_text(str(os.getpid()));time.sleep(1);Path('+repr(str(marker))+').write_text("late");time.sleep(20)'
        parent_code='import subprocess,sys,time;subprocess.Popen([sys.executable,"-c",'+repr(child_code)+'],start_new_session=True);time.sleep(20)'
        with self.assertRaises(b.InterruptedProcess) as caught:
            b.run_process([sys.executable,'-c',parent_code],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=.4)
        self.assertTrue(pidfile.exists())
        self.assertTrue(caught.exception.cleanup_verified)
        time.sleep(.8)
        self.assertFalse(marker.exists())
        child=Path('/proc')/pidfile.read_text()
        if child.exists():
            self.assertEqual((child/'stat').read_text().rsplit(')',1)[1].split()[0],'Z')

    def test_ordinary_uid_nondumpable_child_is_unconfirmed_not_silently_skipped(self):
        uid, gid = os.getuid(), os.getgid()
        options = {}
        if uid == 0:
            account = next(value for value in pwd.getpwall() if value.pw_name == 'nobody')
            uid, gid = account.pw_uid, account.pw_gid
            options = dict(user=uid, group=gid, extra_groups=[])
        self.root.chmod(0o755)
        directory = self.root / 'ordinary-probe'
        directory.mkdir()
        if os.getuid() == 0:
            os.chown(directory, uid, gid)
        probe = r"""
import ctypes,json,os,signal,subprocess,sys,time
from pathlib import Path
sys.path.insert(0,sys.argv[1])
import bootstrap_guest as b
root=Path(sys.argv[2]);pidfile=root/'identity.json'
child_code='''import ctypes,json,os,time;from pathlib import Path
ctypes.CDLL(None).prctl(4,0,0,0,0)
identity=Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]
Path(%r).write_text(json.dumps({'pid':os.getpid(),'start':identity,'token_preserved':bool(os.environ.get('LUDA_BOOTSTRAP_PROCESS_TOKEN'))}))
time.sleep(20)
''' % str(pidfile)
parent_code='import subprocess,sys,time;subprocess.Popen([sys.executable,"-c",'+repr(child_code)+'],start_new_session=True);time.sleep(20)'
try:
 try:
  b.run_process([sys.executable,'-c',parent_code],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=.6)
  raise AssertionError('Interrupted invocation returned success')
 except b.InterruptedProcess as exc:
  value=json.loads(pidfile.read_text());pid=value['pid']
  value.update(uid=os.getuid(),cleanup_verified=exc.cleanup_verified,alive=Path('/proc',str(pid)).exists())
  assert value['token_preserved'] and value['alive'] and not exc.cleanup_verified,value
  print(json.dumps(value))
finally:
 if pidfile.exists():
  value=json.loads(pidfile.read_text());path=Path('/proc',str(value['pid']))
  try:
   if b.process_identity(path)==(os.getuid(),value['start']):os.kill(value['pid'],signal.SIGKILL)
  except (FileNotFoundError,ProcessLookupError):pass
"""
        result=subprocess.run([sys.executable,'-c',probe,str(ROOT/'scripts'),str(directory)],capture_output=True,text=True,timeout=8,**options)
        self.assertEqual(result.returncode,0,result.stderr)
        evidence=json.loads(result.stdout)
        self.assertNotEqual(evidence['uid'],0)
        self.assertFalse(evidence['cleanup_verified'])
        self.assertTrue(evidence['token_preserved'])

    def test_unproved_cleanup_marks_unknown_and_prohibits_automatic_retry(self):
        with patch.object(b,'desktop_status',return_value=self.status()),patch.object(b,'run_process',side_effect=b.InterruptedProcess(False)),patch.object(b,'doctor') as doctor:
            result=self.call()
        self.assertEqual(result['installation_outcome'],'unknown')
        self.assertIsNone(result['installation_completed'])
        self.assertFalse(result['cleanup_verified'])
        self.assertFalse(result['automatic_retry_allowed'])
        doctor.assert_not_called()

    def test_cli_failure_stdout_is_one_json_result(self):
        result = subprocess.run([sys.executable, str(ROOT / 'scripts/bootstrap_guest.py'),
                                 '--source', str(self.source), '--prefix', '/',
                                 '--output', str(self.output), '--user', 'desktop'],
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 1)
        value = json.loads(result.stdout)
        self.assertEqual(value['stage'], 'validation')
        self.assertFalse(value['installation_completed'])
        self.assertEqual(result.stderr, '')

    def test_status_projection_and_incompatible_data_are_redacted(self):
        helper = self.root / 'status helper'
        helper.write_text('fixture')
        def run(argv, **kwargs):
            self.assertEqual(argv, [helper, 'status'])
            kwargs['stdout'].write(json.dumps(self.reply).encode())
            return 0
        with patch.object(b, 'SILO_HELPER', helper), patch.object(b, 'run_process', side_effect=run):
            self.reply = {**self.status(), 'password': 'SENSITIVE', 'display': 'SENSITIVE'}
            self.assertEqual(b.desktop_status('desktop'), self.status())
            for change in ({'version': '2'}, {'installed': False}, {'user': 'other'}, {'state': 'unknown'}):
                self.reply = {**self.status(), **change, 'password': 'SENSITIVE'}
                with self.assertRaises(b.BootstrapError) as caught:
                    b.desktop_status('desktop')
                self.assertNotIn('SENSITIVE', str(caught.exception))


if __name__ == '__main__':
    unittest.main()
