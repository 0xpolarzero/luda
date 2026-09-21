"""Attachment must resolve one intended session and drop identity before exec."""
import os
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from luda import session

class SessionDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
    def fixture(self,pid,env=None,comm='xfce4-session'):
        p=self.root/str(pid);p.mkdir()
        (p/'comm').write_text(comm+'\n')
        (p/'environ').write_bytes(env if env is not None else b'DISPLAY=:7\0DBUS_SESSION_BUS_ADDRESS=unix:path=/session\0TOKEN=never-report-this\0')
    def discover(self,pid=None):
        real=Path
        with patch('luda.session.Path',side_effect=lambda path:real(self.root if path=='/proc' else path)):
            return session.discover(os.getuid(),pid)
    def test_exact_session_and_environment_with_equals(self):
        self.fixture(10);self.fixture(11,comm='other')
        result=self.discover()
        self.assertEqual(result['DISPLAY'],':7')
        self.assertEqual(result['DBUS_SESSION_BUS_ADDRESS'],'unix:path=/session')
    def test_explicit_pid_accepts_other_session_manager_without_guessing(self):
        self.fixture(12, comm='other-session')
        with self.assertRaises(SystemExit): self.discover()
        self.assertEqual(self.discover(12)['DISPLAY'], ':7')
    def test_explicit_pid_still_requires_selected_account(self):
        self.fixture(12, comm='other-session')
        with patch('luda.session.os.getuid', return_value=999999), self.assertRaises(SystemExit): self.discover(12)
    def test_ambiguous_requires_explicit_session(self):
        self.fixture(10);self.fixture(11)
        with self.assertRaises(SystemExit) as caught:self.discover()
        self.assertNotIn('never-report',str(caught.exception))
        self.assertEqual(self.discover(11)['DISPLAY'],':7')
    def test_missing_or_invalid_environment_is_not_guessed(self):
        for env in (b'DISPLAY=:7\0',b'DBUS_SESSION_BUS_ADDRESS=x\0',b'\xff=X\0'):
            with self.subTest(env=env):
                self.fixture(10,env)
                with self.assertRaises(SystemExit):self.discover()
                import shutil;shutil.rmtree(self.root/'10')
    def test_nonexistent_explicit_pid_does_not_fallback(self):
        self.fixture(10)
        with self.assertRaises(SystemExit):self.discover(999)
    def test_vanished_or_unreadable_candidate_is_ignored(self):
        (self.root/'10').mkdir();self.fixture(11)
        self.assertEqual(self.discover()['DISPLAY'],':7')

class SessionWaitTests(unittest.TestCase):
    def test_missing_session_retried_until_ready(self):
        with patch('luda.session.discover',side_effect=[session.SessionDiscoveryError(0),{'DISPLAY':':7'}]) as discover,patch('luda.session.time.sleep'):
            self.assertEqual(session.wait_for_session(1001,123,1),{'DISPLAY':':7'})
        self.assertEqual(discover.call_count,2)
        discover.assert_called_with(1001,123)
    def test_ambiguous_session_is_not_retried(self):
        with patch('luda.session.discover',side_effect=session.SessionDiscoveryError(2)),patch('luda.session.time.sleep') as sleep,self.assertRaises(SystemExit):session.wait_for_session(1001,timeout=1)
        sleep.assert_not_called()
    def test_deadline_and_zero_timeout_are_bounded(self):
        for times,timeout in (([0,0,0,2],1),([0,0],0)):
            with patch('luda.session.discover',side_effect=session.SessionDiscoveryError(0)),patch('luda.session.elapsed_time',side_effect=times),patch('luda.session.time.sleep'),self.assertRaises(SystemExit):session.wait_for_session(1001,timeout=timeout)

class SessionLaunchTests(unittest.TestCase):
    def setup_launch(self,uid=0):
        account=SimpleNamespace(pw_uid=1001,pw_gid=1002,pw_name='desktop',pw_dir='/home/desktop')
        values={'DISPLAY':':7','DBUS_SESSION_BUS_ADDRESS':'unix:path=/bus','XAUTHORITY':'/home/desktop/auth',
                'XDG_RUNTIME_DIR':'/run/user/1001','LD_PRELOAD':'untrusted','TOKEN':'private'}
        patches=[patch('sys.argv',['luda-session','--user','desktop','--','/opt/luda','--flag']),
                 patch('luda.session.pwd.getpwnam',return_value=account),patch('luda.session.discover',return_value=values),
                 patch('luda.session.os.getuid',return_value=uid),patch('luda.session.Path.is_file',return_value=True),patch('luda.session.os.chdir')]
        for p in patches:p.start();self.addCleanup(p.stop)
    def test_omitted_user_resolves_current_uid_without_named_account(self):
        self.setup_launch(1001)
        account=SimpleNamespace(pw_uid=1001,pw_gid=1002,pw_name='generic',pw_dir='/home/generic')
        with patch('sys.argv',['luda-session','--','/opt/luda']), patch('luda.session.pwd.getpwuid',return_value=account) as lookup, patch('luda.session.os.execvpe') as execute:
            session.main()
        lookup.assert_called_once_with(1001)
        self.assertEqual(execute.call_args.args[2]['USER'],'generic')
    def test_launch_preserves_selected_desktop_identity_without_inheriting_callers(self):
        self.setup_launch(1001)
        keys = ('XDG_CURRENT_DESKTOP', 'XDG_SESSION_DESKTOP', 'DESKTOP_SESSION')
        for identity in ({}, dict(zip(keys, ('Example:Secondary', 'example', 'example-session')))):
            with self.subTest(identity=identity), patch.dict(os.environ, dict.fromkeys(keys, 'caller-desktop')), \
                    patch('luda.session.discover', return_value={
                        'DISPLAY': ':7', 'DBUS_SESSION_BUS_ADDRESS': 'unix:path=/bus', **identity}), \
                    patch('luda.session.os.execvpe') as execute:
                session.main()
                env = execute.call_args.args[2]
                self.assertEqual({key: env[key] for key in keys if key in env}, identity)

    def test_privilege_drop_precedes_exec_and_environment_is_allowlisted(self):
        self.setup_launch();events=[]
        def capture(name):return lambda *args:events.append((name,args))
        with patch('luda.session.os.initgroups',side_effect=capture('groups')),patch('luda.session.os.setgid',side_effect=capture('gid')),patch('luda.session.os.setuid',side_effect=capture('uid')),patch('luda.session.os.chdir',side_effect=capture('cwd')),patch('luda.session.os.execvpe',side_effect=capture('exec')):
            session.main()
        self.assertEqual([e[0] for e in events],['groups','gid','uid','cwd','exec'])
        argv,env=events[-1][1][1:]
        self.assertEqual(argv,['/opt/luda','--flag']);self.assertEqual(env['DISPLAY'],':7')
        self.assertNotIn('TOKEN',env);self.assertNotIn('LD_PRELOAD',env)
        self.assertEqual(env['HOME'],'/home/desktop')
    def test_browser_selection_checked_after_drop_without_ambient_passthrough(self):
        self.setup_launch();events=[]
        with patch('luda.session.os.initgroups'),patch('luda.session.os.setgid'),patch('luda.session.os.setuid',side_effect=lambda uid:events.append('drop')),patch('luda.managed_browser.selected',side_effect=lambda prefix:events.append('verify') or dict(executable='/verified/chrome',version='1.2.3.4',sha256='a'*64,architecture='aarch64')),patch.dict(os.environ,{'LUDA_CHROMIUM_EXECUTABLE':'/ambient/untrusted'}),patch('luda.session.os.execvpe') as execute:
            session.main()
        self.assertEqual(events,['drop','verify'])
        self.assertEqual(execute.call_args.args[2]['LUDA_CHROMIUM_EXECUTABLE'],'/verified/chrome')
        with patch('luda.session.os.initgroups'),patch('luda.session.os.setgid'),patch('luda.session.os.setuid'),patch('luda.managed_browser.selected',side_effect=ValueError('changed')),patch('luda.session.os.execvpe') as execute,self.assertRaises(SystemExit):session.main()
        execute.assert_not_called()
    def test_inaccessible_home_uses_accessible_root_before_exec(self):
        self.setup_launch(1001)
        with patch('luda.session.os.chdir',side_effect=[PermissionError(),None]) as cwd,patch('luda.session.os.execvpe') as execute:
            session.main()
        self.assertEqual([call.args for call in cwd.call_args_list],[('/home/desktop',),('/',)])
        execute.assert_called_once()
    def test_explicit_working_directory_failure_does_not_fallback_or_execute(self):
        self.setup_launch(1001)
        with patch('sys.argv',['luda-session','--cwd','/private','--','/opt/luda']),patch('luda.session.os.chdir',side_effect=PermissionError()) as cwd,patch('luda.session.os.execvpe') as execute,self.assertRaises(SystemExit):
            session.main()
        cwd.assert_called_once_with('/private');execute.assert_not_called()
    def test_relative_executable_is_resolved_before_changing_directory(self):
        self.setup_launch(1001)
        expected=os.path.abspath('./bin/luda')
        with patch('sys.argv',['luda-session','--cwd','/workspace','--','./bin/luda','relative-argument']),patch('luda.session.os.chdir') as cwd,patch('luda.session.os.execvpe') as execute:
            session.main()
        cwd.assert_called_once_with('/workspace')
        self.assertEqual(execute.call_args.args[:2],(expected,[expected,'relative-argument']))
    def test_unrelated_account_cannot_attach(self):
        self.setup_launch(1003)
        with patch('luda.session.os.execvpe') as execute,self.assertRaises(SystemExit):session.main()
        execute.assert_not_called()
    def test_desktop_account_executes_without_privilege_calls(self):
        self.setup_launch(1001)
        with patch('luda.session.os.initgroups') as groups,patch('luda.session.os.setgid') as gid,patch('luda.session.os.setuid') as uid,patch('luda.session.os.execvpe') as execute:
            session.main()
        groups.assert_not_called();gid.assert_not_called();uid.assert_not_called();execute.assert_called_once()
    def test_missing_authority_prevents_exec(self):
        self.setup_launch()
        with patch('luda.session.Path.is_file',return_value=False),patch('luda.session.os.execvpe') as execute,self.assertRaises(SystemExit):session.main()
        execute.assert_not_called()

if __name__=='__main__':unittest.main()
