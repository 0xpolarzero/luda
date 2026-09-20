import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'integrations/silo'
spec = importlib.util.spec_from_file_location('silo_tools', ASSETS / 'guest/agent-tools.py')
tools = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tools)
COMMIT = '1' * 40
RELEASE = {'schema_version': 1, 'enabled': True, 'source_commit': COMMIT,
           'source_sha256': '2' * 64, 'source_url': 'https://example.invalid/luda.tar.gz'}
REQUIRED = ('pyproject.toml', 'MANIFEST.in', 'requirements.lock', 'build-requirements.lock',
            'scripts/bootstrap_guest.py', 'scripts/manage_install.py', 'scripts/install.sh',
            'src/luda/server.py', 'skills/luda/SKILL.md')


def archive(path, extra=None, missing=None):
    with tarfile.open(path, 'w:gz') as output:
        for name in REQUIRED:
            if name == missing:
                continue
            value = b'fixture'
            info = tarfile.TarInfo('luda-' + COMMIT + '/' + name)
            info.size = len(value)
            output.addfile(info, io.BytesIO(value))
        if extra:
            output.addfile(extra, io.BytesIO(b'x' * extra.size))


class SiloIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.state = Path(self.temp.name)
        self.fetch = lambda release, path: archive(path)
        self.install = Mock(return_value={'ok': True, 'installation_completed': True,
                                         'configuration_generated': True, 'tools': {'ready': True},
                                         'selected_release': '0.1.0-' + 'a' * 16})

    def ensure(self, release=None, **kwargs):
        return tools.ensure(release or RELEASE, self.state, fetch=self.fetch,
                            install=self.install, running=lambda: True, **kwargs)

    def test_optional_browser_explicit_enable_disable_and_identity(self):
        candidate=dict(schema_version=1,executable='/opt/trusted/chrome',sha256='a'*64,version='153.0.8010.12',architecture='aarch64')
        release={**RELEASE,'browser':candidate}
        # Extend the authored archive with the actual capability files expected
        # by the wrapper, without pretending this mocked installer launches UI.
        def fetch(value,path):
            with tarfile.open(path,'w:gz') as output:
                for name in (*REQUIRED,'requirements-browser.lock','src/luda/managed_browser.py'):
                    info=tarfile.TarInfo('luda-'+COMMIT+'/'+name);info.size=7;output.addfile(info,io.BytesIO(b'fixture'))
        base=tools.ensure(release,self.state,fetch=fetch,install=self.install,running=lambda:True)
        self.assertFalse(base['browser_requested']);self.assertFalse(base['browser_configured'])
        count=self.install.call_count
        self.assertTrue(tools.status(release,self.state)['browser_available']);self.assertEqual(self.install.call_count,count)
        enabled=tools.set_browser(release,self.state,True,fetch=fetch,install=self.install,running=lambda:True)
        self.assertTrue(enabled['browser_configured']);self.assertNotEqual(base['browser_config_sha256'],enabled['browser_config_sha256'])
        config=self.install.call_args.kwargs['browser_config'];self.assertEqual(json.loads(config.read_text()),candidate)
        changed={**release,'browser':{**candidate,'version':'154.0.0.0'}}
        self.assertEqual(tools.status(changed,self.state)['state'],'update_available')
        self.assertEqual(tools.status(RELEASE,self.state)['reason'],'browser_candidate_unavailable')
        disabled=tools.set_browser(RELEASE,self.state,False,fetch=fetch,install=self.install,running=lambda:True)
        self.assertFalse(disabled['browser_configured']);self.assertEqual(disabled['browser_config_sha256'],base['browser_config_sha256'])
        self.assertEqual(self.install.call_args.kwargs,{})
    def test_incomplete_bootstrap_never_claims_completed_browser_setup(self):
        candidate=dict(schema_version=1,executable='/opt/trusted/chrome',sha256='a'*64,version='153.0.8010.12',architecture='aarch64')
        release={**RELEASE,'browser':candidate}
        def fetch(value,path):
            with tarfile.open(path,'w:gz') as output:
                for name in (*REQUIRED,'requirements-browser.lock','src/luda/managed_browser.py'):
                    info=tarfile.TarInfo('luda-'+COMMIT+'/'+name);info.size=1;output.addfile(info,io.BytesIO(b'x'))
        complete={'ok':True,'installation_completed':True,'configuration_generated':True,'tools':{'ready':True}}
        for changes in ({'installation_completed':False},{'configuration_generated':False},{'tools':{'ready':False}},{'ok':False}):
            with self.subTest(changes=changes):
                self.install.return_value={**complete,**changes}
                value=tools.set_browser(release,self.state,True,fetch=fetch,install=self.install,running=lambda:True)
                self.assertEqual(value['state'],'attention')
                self.assertIsNone(value['browser_configured'])
                self.assertIsNone(tools.status(release,self.state)['browser_configured'])
        self.install.return_value=complete
        value=tools.set_browser(release,self.state,True,fetch=fetch,install=self.install,running=lambda:True)
        self.assertEqual(value['state'],'ready');self.assertTrue(value['browser_configured'])

    def test_browser_source_without_managed_api_refuses_without_install_or_retry(self):
        candidate=dict(schema_version=1,executable='/opt/trusted/chrome',sha256='a'*64,version='153.0.8010.12',architecture='aarch64')
        release={**RELEASE,'browser':candidate}
        value=tools.set_browser(release,self.state,True,fetch=self.fetch,install=self.install,running=lambda:True)
        self.assertEqual(value['reason'],'browser_source_unsupported')
        self.assertIs(value['installation_completed'],False)
        self.assertTrue(value['browser_requested']);self.install.assert_not_called()
        again=tools.ensure(release,self.state,fetch=self.fetch,install=self.install,running=lambda:True)
        self.assertEqual(again['state'],'attention');self.install.assert_not_called()

    def test_optional_browser_missing_bad_candidate_and_uncertainty_refuse(self):
        with self.assertRaises(tools.OnboardingError):tools.set_browser(RELEASE,self.state,True)
        self.assertFalse((self.state/'browser-selection.json').exists())
        with self.assertRaises(tools.OnboardingError):tools.browser_candidate({'schema_version':True})
        tools.atomic(self.state/'status.json',{'state':'unconfirmed'})
        with self.assertRaises(tools.OnboardingError):tools.set_browser(RELEASE,self.state,False)
        self.install.assert_not_called()

    def test_manifest_disabled_by_default_and_strictly_validated(self):
        self.assertFalse(tools.manifest(ASSETS / 'guest/agent-tools-release.json')['enabled'])
        candidates = [dict(RELEASE, source_commit='main'), dict(RELEASE, source_sha256='bad'),
                      dict(RELEASE, source_url='http://example.invalid/file'),
                      dict(RELEASE, source_url='https://secret@example.invalid/file'),
                      dict(RELEASE, source_url='https://example.invalid/file?token=secret'),
                      dict(RELEASE, unknown='secret'), {'schema_version': 1, 'enabled': 1}]
        path = self.state / 'manifest.json'
        for value in candidates:
            path.write_text(json.dumps(value))
            with self.subTest(value=value), self.assertRaises(tools.OnboardingError):
                tools.manifest(path)
        path.write_text(json.dumps(RELEASE))
        self.assertEqual(tools.manifest(path), RELEASE)

    def test_disabled_does_not_probe_desktop_or_install(self):
        running = Mock(side_effect=AssertionError('must not probe'))
        result = tools.ensure({'enabled': False}, self.state, running=running, install=self.install)
        self.assertEqual(result['state'], 'unconfigured')
        self.install.assert_not_called()
        self.assertFalse((self.state / 'status.json').exists())

    def test_stopped_defers_and_later_running_installs_once(self):
        result = tools.ensure(RELEASE, self.state, running=lambda: False, install=self.install)
        self.assertEqual(result['state'], 'pending')
        self.install.assert_not_called()
        result = self.ensure()
        self.assertEqual(result['state'], 'ready')
        self.ensure()
        self.install.assert_called_once()
        self.assertNotIn('source_url', result)

    def test_preflight_failure_is_durable_and_never_reverts_to_pending(self):
        probe = Mock(side_effect=FileNotFoundError('sensitive helper path'))
        result = tools.ensure(RELEASE, self.state, running=probe, install=self.install)
        self.assertEqual(result['state'], 'attention')
        self.assertIs(result['installation_completed'], False)
        self.assertEqual(result['reason'], 'desktop_status_unavailable')
        self.assertEqual(tools.status(RELEASE, self.state), result)
        self.assertNotIn('sensitive', json.dumps(result))
        self.ensure()
        self.install.assert_not_called()

    def test_install_observes_durable_uncertain_marker_and_fresh_output(self):
        original = self.install.return_value
        def inspect(source, output):
            state = tools.read_json(self.state / 'status.json')
            self.assertEqual(state['state'], 'unconfirmed')
            self.assertIsNone(state['installation_completed'])
            self.assertFalse(output.exists())
            self.assertTrue((source / 'requirements.lock').exists())
            return original
        self.install.side_effect = inspect
        self.assertEqual(self.ensure()['state'], 'ready')

    def test_failed_and_interrupted_attempts_never_auto_retry(self):
        self.install.side_effect = RuntimeError('sensitive diagnostic')
        result = self.ensure()
        self.assertEqual(result['state'], 'unconfirmed')
        self.assertIsNone(result['installation_completed'])
        self.assertNotIn('sensitive', json.dumps(result))
        self.ensure()
        self.install.assert_called_once()
        self.assertFalse(result['automatic_retry_allowed'])
        self.ensure(reviewed=True)
        self.assertEqual(self.install.call_count, 2)

    def test_external_interruption_preserves_marker(self):
        self.install.side_effect = KeyboardInterrupt
        with self.assertRaises(KeyboardInterrupt):
            self.ensure()
        self.install.side_effect = None
        result = self.ensure()
        self.assertEqual(result['state'], 'unconfirmed')
        self.install.assert_called_once()

    def test_installed_not_ready_remains_installed_and_no_automatic_update(self):
        self.install.return_value.update(ok=False, configuration_generated=False, tools={'ready': False})
        result = self.ensure()
        self.assertEqual(result['state'], 'attention')
        self.assertTrue(result['installation_completed'])
        self.assertFalse(result['last_ready'])
        self.ensure(dict(RELEASE, source_sha256='3' * 64))
        self.install.assert_called_once()

    def test_new_manifest_reports_update_without_install(self):
        self.ensure()
        result = self.ensure(dict(RELEASE, source_sha256='3' * 64))
        self.assertEqual(result['state'], 'update_available')
        self.install.assert_called_once()

    def test_status_always_compares_current_manifest_without_install(self):
        self.ensure()
        changed = dict(RELEASE, source_sha256='3' * 64)
        self.assertEqual(tools.status(changed, self.state)['state'], 'update_available')
        self.assertEqual(tools.status({'enabled': False}, self.state)['state'], 'unconfigured')
        self.assertEqual(tools.status(RELEASE, self.state)['state'], 'ready')
        self.install.assert_called_once()

    def test_extracted_skill_modes_survive_installer_copytree(self):
        import shutil
        path = self.state / 'source.tar.gz';archive(path)
        import os
        previous = os.umask(0o077)
        try:
            source = tools.extract(path, self.state / 'extract', COMMIT)
        finally:
            os.umask(previous)
        installed = self.state / 'release' / 'skills'
        shutil.copytree(source / 'skills', installed)
        self.assertEqual((installed / 'luda').stat().st_mode & 0o777, 0o755)
        self.assertEqual((installed / 'luda/SKILL.md').stat().st_mode & 0o777, 0o644)
        self.assertEqual((self.state / 'extract').stat().st_mode & 0o777, 0o700)

    def test_wrapper_nonblocking_lock_prevents_concurrent_install(self):
        import contextlib
        import fcntl
        lock = (self.state / 'operation.lock').open('w')
        self.addCleanup(lock.close)
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        original_stat = Path.stat
        def pretend_root_owned(path, *args, **kwargs):
            from types import SimpleNamespace
            result = original_stat(path, *args, **kwargs)
            return SimpleNamespace(st_uid=0, st_mode=result.st_mode) if path == self.state else result
        with patch.object(Path, 'stat', pretend_root_owned), patch.object(tools, 'STATE', self.state), patch.object(tools.os, 'geteuid', return_value=0), patch.object(tools, 'manifest', return_value=RELEASE), patch.object(tools, 'ensure') as ensure, patch.object(tools.sys, 'argv', ['agent-tools.py', 'ensure']), contextlib.redirect_stdout(io.StringIO()) as output:
            tools.main()
        ensure.assert_not_called()
        self.assertEqual(json.loads(output.getvalue())['state'], 'unconfirmed')
        self.assertEqual(json.loads(output.getvalue())['reason'], 'operation_busy')

    def test_download_checksum_and_https_redirect(self):
        data = b'archive bytes'
        response = io.BytesIO(data)
        response.geturl = lambda: RELEASE['source_url']
        opener = Mock()
        opener.open.return_value = response
        with patch.object(tools.urllib.request, 'build_opener', return_value=opener):
            with self.assertRaises(tools.OnboardingError):
                tools.download(RELEASE, self.state / 'wrong.tar.gz')
        with self.assertRaises(tools.OnboardingError):
            tools.HttpsRedirect().redirect_request(None, None, 302, '', {}, 'http://example.invalid/no')
        response = io.BytesIO(data)
        response.geturl = lambda: RELEASE['source_url']
        opener.open.return_value = response
        with patch.object(tools.urllib.request, 'build_opener', return_value=opener):
            tools.download(dict(RELEASE, source_sha256=hashlib.sha256(data).hexdigest()), self.state / 'valid.tar.gz')

    def test_whole_download_deadline_interrupts_trickled_http_body(self):
        import http.client
        import socket
        import threading
        import time
        client, server = socket.socketpair()
        client.settimeout(.2)
        stopped = threading.Event()
        def trickle():
            try:
                server.sendall(b'HTTP/1.1 200 OK\r\nContent-Length: 100000\r\n\r\n')
                while not stopped.wait(.02):
                    server.sendall(b'x')
            except OSError:
                pass
        thread = threading.Thread(target=trickle, daemon=True);thread.start()
        response = http.client.HTTPResponse(client);response.begin()
        response.geturl = lambda: RELEASE['source_url']
        opener = Mock();opener.open.return_value = response
        began = time.monotonic()
        prior_handler = tools.signal.getsignal(tools.signal.SIGALRM)
        try:
            with patch.object(tools.urllib.request, 'build_opener', return_value=opener), self.assertRaisesRegex(tools.OnboardingError, 'download_timeout'):
                tools.download(RELEASE, self.state / 'slow.tar.gz', timeout=.15)
            self.assertLess(time.monotonic()-began, 1)
            self.assertEqual(tools.signal.getitimer(tools.signal.ITIMER_REAL), (0.0, 0.0))
            self.assertEqual(tools.signal.getsignal(tools.signal.SIGALRM), prior_handler)
        finally:
            stopped.set();client.close();server.close();thread.join(timeout=1)

    def test_download_deadline_covers_header_wait_and_rejects_active_timer(self):
        import signal
        import time
        opener = Mock()
        opener.open.side_effect = lambda *args, **kwargs: time.sleep(1)
        with patch.object(tools.urllib.request, 'build_opener', return_value=opener), self.assertRaisesRegex(tools.OnboardingError, 'download_timeout'):
            tools.download(RELEASE, self.state / 'headers.tar.gz', timeout=.05)
        self.assertEqual(signal.getitimer(signal.ITIMER_REAL), (0.0, 0.0))
        previous = signal.getsignal(signal.SIGALRM)
        signal.setitimer(signal.ITIMER_REAL, 10)
        try:
            with self.assertRaisesRegex(tools.OnboardingError, 'download_timer_in_use'):
                tools.download(RELEASE, self.state / 'timer.tar.gz')
            self.assertGreater(signal.getitimer(signal.ITIMER_REAL)[0], 0)
            self.assertEqual(signal.getsignal(signal.SIGALRM), previous)
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)

    def test_archive_rejects_traversal_links_duplicates_and_missing_locks(self):
        cases = []
        traversal = tarfile.TarInfo('luda-' + COMMIT + '/../escape');cases.append(traversal)
        link = tarfile.TarInfo('luda-' + COMMIT + '/link');link.type = tarfile.SYMTYPE;link.linkname = '/etc';cases.append(link)
        hardlink = tarfile.TarInfo('luda-' + COMMIT + '/hardlink');hardlink.type = tarfile.LNKTYPE;hardlink.linkname = 'pyproject.toml';cases.append(hardlink)
        cases.append(tarfile.TarInfo('luda-' + COMMIT + '/pyproject.toml'))
        for index, member in enumerate(cases):
            path = self.state / f'bad-{index}.tar.gz';archive(path, extra=member)
            with self.subTest(index=index), self.assertRaises((tools.OnboardingError, FileExistsError)):
                tools.extract(path, self.state / f'extract-{index}', COMMIT)
        path = self.state / 'missing.tar.gz';archive(path, missing='requirements.lock')
        with self.assertRaises(tools.OnboardingError):
            tools.extract(path, self.state / 'missing', COMMIT)
        self.assertFalse((self.state / 'escape').exists())

    def test_projection_excludes_untrusted_text_paths_and_fake_booleans(self):
        value = tools.project({'state': 'secret', 'installation_completed': 'true', 'last_ready': 1,
                               'source_url': 'secret', 'selected_release': '/private/secret',
                               'checked_at': 'secret', 'error': 'secret', 'password': 'secret'})
        self.assertEqual(value['state'], 'unconfirmed')
        self.assertIsNone(value['installation_completed'])
        self.assertIsNone(value['last_ready'])
        self.assertNotIn('secret', json.dumps(value))

    def test_ready_projection_requires_consistent_success_fields(self):
        valid = {'state': 'ready', 'installation_completed': True,
                 'configuration_generated': True, 'last_ready': True}
        self.assertEqual(tools.project(valid)['state'], 'ready')
        for key in ('installation_completed', 'configuration_generated', 'last_ready'):
            for value in (None, False, 1, 'true', [], {}):
                with self.subTest(key=key, value=value):
                    self.assertEqual(tools.project({**valid, key: value})['state'], 'unconfirmed')
            missing = dict(valid);missing.pop(key)
            self.assertEqual(tools.project(missing)['state'], 'unconfirmed')

    def test_projection_handles_nonstring_states_and_reasons(self):
        for value in ([], {}, ['ready'], {'state': 'ready'}, 1, True):
            with self.subTest(value=value):
                projected = tools.project({'state': value, 'reason': value})
                self.assertEqual(projected['state'], 'unconfirmed')
                self.assertNotIn('reason', projected)

    def test_desktop_probe_only_uses_status_and_never_starts(self):
        def run(argv, **kwargs):
            self.assertEqual(argv, ['/usr/local/bin/silo-desktop', 'status'])
            kwargs['stdout'].write(json.dumps({'version': '1', 'installed': True,
                                             'user': 'silo-desktop', 'state': 'stopped', 'password': 'secret'}).encode())
            return subprocess.CompletedProcess(argv, 0)
        with patch.object(tools.subprocess, 'run', side_effect=run):
            self.assertFalse(tools.desktop_running())

    def test_guest_patch_applies_and_matches_canonical_assets(self):
        checkout = self.state / 'checkout';checkout.mkdir()
        subprocess.run(['git', 'init', '-q', str(checkout)], check=True)
        spec = importlib.util.spec_from_file_location('silo_guest_apply', ASSETS / 'apply.py')
        module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        for name in module.PATCHES:
            subprocess.run(['git', '-C', str(checkout), 'apply', '--allow-empty', '--include=app/SiloUI/src-tauri/guest/agent-tools*', str(ASSETS / name)], check=True)
        for name in ('agent-tools.py', 'agent-tools-release.json'):
            self.assertEqual((checkout / 'app/SiloUI/src-tauri/guest' / name).read_bytes(),
                             (ASSETS / 'guest' / name).read_bytes())

    def test_native_patch_embeds_exact_reviewed_skill(self):
        checkout = self.state / 'native';checkout.mkdir()
        subprocess.run(['git', 'init', '-q', str(checkout)], check=True)
        target = 'app/SiloUI/src-tauri/guest/luda-codex-skill.md'
        spec = importlib.util.spec_from_file_location('silo_skill_apply', ASSETS / 'apply.py')
        module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        for name in module.PATCHES:
            subprocess.run(['git', '-C', str(checkout), 'apply', '--allow-empty', '--include=' + target,
                            str(ASSETS / name)], check=True)
        self.assertEqual((checkout / target).read_bytes(), (ROOT / 'skills/luda/SKILL.md').read_bytes())

    def test_ordered_patch_check_isolated_from_checkout_and_index(self):
        spec = importlib.util.spec_from_file_location('silo_apply', ASSETS / 'apply.py')
        module = importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        checkout = self.state / 'ordered';checkout.mkdir()
        def git(*args):
            return subprocess.run(['git', '-C', str(checkout), *args], check=True, capture_output=True, text=True).stdout
        git('init', '-q');git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '--allow-empty', '-qm', 'base')
        assets = self.state / 'patches';assets.mkdir()
        names = module.PATCHES
        previous = ''
        for index, name in enumerate(names):
            content = previous + str(index) + '\n'
            (checkout / 'new.txt').write_text(content)
            git('add', 'new.txt')
            (assets / name).write_text(git('diff', '--cached', '--binary'))
            git('-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'patch')
            previous = content
        git('reset', '--hard', f'HEAD~{len(names)}')
        before = git('write-tree')
        with patch.object(module, 'BASE', git('rev-parse', 'HEAD').strip()), patch.object(module, 'ASSETS', assets):
            module.apply(checkout)
            self.assertFalse((checkout / 'new.txt').exists())
            self.assertEqual(git('write-tree'), before)
            valid = (assets / names[-1]).read_text()
            (assets / names[-1]).write_text('invalid patch')
            with self.assertRaises(ValueError): module.apply(checkout, True)
            self.assertFalse((checkout / 'new.txt').exists())
            self.assertEqual(git('write-tree'), before)
            (assets / names[-1]).write_text(valid)
            module.apply(checkout, True)
            self.assertEqual((checkout / 'new.txt').read_text(), previous)
            self.assertEqual(git('write-tree'), before)
