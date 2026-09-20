"""Fixed-VM host bundles preserve skill bytes and quote the remote shell boundary."""
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('host_builder',ROOT/'scripts/build_plugin.py')
builder=importlib.util.module_from_spec(spec);spec.loader.exec_module(builder)

class HostPlugin(unittest.TestCase):
    def test_remote_shell_preserves_literal_prefix_and_fixed_guest_arguments(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);prefix=root/"guest $(touch SHOULD_NOT_EXIST) quote'";binpath=prefix/'current/.venv/bin';binpath.mkdir(parents=True)
            launcher=binpath/'luda-session';launcher.write_text('#!/usr/bin/python3\nimport json,sys\nprint(json.dumps(sys.argv[1:]))\n');launcher.chmod(0o700)
            server=builder.host_ssh_config(prefix,'silo-desktop','/usr/bin/ssh',root/'private config','silo-vm')['mcpServers']['luda']
            result=subprocess.run(['/bin/sh','-c',server['args'][-1]],cwd=root,capture_output=True,text=True,check=True)
            self.assertEqual(json.loads(result.stdout),['--user','silo-desktop','--',str(binpath/'luda')])
            self.assertFalse((root/'SHOULD_NOT_EXIST').exists())
            self.assertNotIn('experimental_environment',server)
            self.assertIn('StrictHostKeyChecking=yes',server['args'])
            for alias in ('-oProxyCommand=bad','host;echo bad','host\nother'):
                with self.assertRaises(ValueError):builder.host_ssh_config(prefix,'silo-desktop','/usr/bin/ssh',root/'config',alias)

    def test_two_vm_bundles_have_distinct_identity_and_exact_verified_skill(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);skill=ROOT/'skills/luda/SKILL.md';digest=hashlib.sha256(skill.read_bytes()).hexdigest();names=[]
            for suffix in ('1','2'):
                output=root/suffix;vm='00000000-0000-0000-0000-'+suffix.zfill(12)
                builder.build_host_marketplace(output,'/opt/luda',vm,skill,digest,root/'ssh_config','silo-'+suffix)
                meta=json.loads((output/'host-registration.json').read_text());names.append(meta['plugin'])
                self.assertEqual((output/'plugins'/meta['plugin']/'skills/luda/SKILL.md').read_bytes(),skill.read_bytes())
                with self.assertRaises(FileExistsError):builder.build_host_marketplace(output,'/opt/luda',vm,skill,digest,root/'ssh_config','silo-'+suffix)
            self.assertNotEqual(*names)
            with self.assertRaises(ValueError):builder.build_host_marketplace(root/'bad','/opt/luda',vm,skill,'0'*64,root/'ssh_config','silo')
            self.assertFalse((root/'bad').exists())

spec=importlib.util.spec_from_file_location('host_registration',ROOT/'scripts/register_host_plugin.py')
registration=importlib.util.module_from_spec(spec);spec.loader.exec_module(registration)

class HostRegistration(unittest.TestCase):
    def setUp(self):
        import shutil
        self.codex=shutil.which('codex')
        if not self.codex:self.skipTest('Codex CLI unavailable')
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.home=self.root/'profile';self.home.mkdir()
        (self.home/'config.toml').write_text('model = "preserve-test-model"\n')
        self.skill=ROOT/'skills/luda/SKILL.md';self.digest=hashlib.sha256(self.skill.read_bytes()).hexdigest()
    def bundle(self,suffix,folder=None):
        vm='00000000-0000-0000-0000-'+str(suffix).zfill(12)
        out=self.root/(folder or str(suffix))
        builder.build_host_marketplace(out,'/opt/luda',vm,self.skill,self.digest,self.root/'ssh config','silo-'+str(suffix))
        return out
    def test_real_cli_two_vm_registration_cache_and_idempotency(self):
        one=self.bundle(1);two=self.bundle(2)
        first=registration.register(one,self.codex,self.home)
        second=registration.register(two,self.codex,self.home)
        self.assertEqual(first['status'],'registered');self.assertEqual(second['status'],'registered')
        self.assertNotEqual(first['plugin_id'],second['plugin_id'])
        # Plugin listing is not resolved MCP configuration: Codex flattens keys.
        effective=registration.cli(self.codex,self.home,'mcp','list')
        self.assertEqual({entry['name'] for entry in effective},{first['server_name'],second['server_name']})
        self.assertEqual({entry['transport']['args'][-2] for entry in effective},{'silo-1','silo-2'})
        self.assertEqual({entry['name']:entry['transport']['args'][-2] for entry in effective},
                         {first['server_name']:'silo-1',second['server_name']:'silo-2'})
        before=(self.home/'config.toml').read_bytes()
        again=registration.register(one,self.codex,self.home)
        self.assertEqual(again['status'],'already_registered')
        self.assertEqual((self.home/'config.toml').read_bytes(),before)
        self.assertIn(b'preserve-test-model',before)
        meta=json.loads((one/'host-registration.json').read_text())
        cached=self.home/'plugins/cache'/meta['marketplace']/meta['plugin']/meta['version']
        self.assertEqual((cached/'skills/luda/SKILL.md').read_bytes(),self.skill.read_bytes())
        self.assertEqual(json.loads((cached/'.mcp.json').read_text()),json.loads((one/'plugins'/meta['plugin']/'.mcp.json').read_text()))
        conflict=self.bundle(1,'different-location')
        with self.assertRaisesRegex(registration.RegistrationError,'registration_conflict'):registration.register(conflict,self.codex,self.home)
        self.assertEqual((self.home/'config.toml').read_bytes(),before)
    def test_partial_cli_failure_preserves_marketplace_and_refuses_blind_retry(self):
        bundle=self.bundle(3);calls=[]
        def failing(executable,home,*args):
            calls.append(args)
            if args[:2]==('plugin','add'):raise RuntimeError('SYNTHETIC_PRIVATE_ERROR')
            return registration.cli(executable,home,*args)
        result=registration.register(bundle,self.codex,self.home,runner=failing)
        self.assertEqual(result['status'],'unconfirmed');self.assertEqual(result['stage'],'plugin_add')
        self.assertNotIn('SYNTHETIC_PRIVATE_ERROR',json.dumps(result))
        markets=registration.cli(self.codex,self.home,'plugin','marketplace','list')
        self.assertEqual(len(markets['marketplaces']),1)
        before=(self.home/'config.toml').read_bytes()
        with self.assertRaisesRegex(registration.RegistrationError,'previous_attempt_requires_review'):registration.register(bundle,self.codex,self.home)
        self.assertEqual((self.home/'config.toml').read_bytes(),before)
    def test_disabled_existing_plugin_is_not_silently_enabled(self):
        bundle=self.bundle(4);registration.register(bundle,self.codex,self.home)
        config=self.home/'config.toml';config.write_text(config.read_text().replace('enabled = true','enabled = false'))
        before=config.read_bytes()
        with self.assertRaisesRegex(registration.RegistrationError,'installed_plugin_conflict'):registration.register(bundle,self.codex,self.home)
        self.assertEqual(config.read_bytes(),before)
    def test_lost_install_reply_can_be_verified_without_replaying_add(self):
        bundle=self.bundle(5)
        def lost_reply(executable,home,*args):
            value=registration.cli(executable,home,*args)
            if args[:2]==('plugin','add'):raise RuntimeError('lost reply')
            return value
        self.assertEqual(registration.register(bundle,self.codex,self.home,runner=lost_reply)['status'],'unconfirmed')
        def reads_only(executable,home,*args):
            self.assertNotIn('add',args)
            return registration.cli(executable,home,*args)
        self.assertEqual(registration.register(bundle,self.codex,self.home,runner=reads_only)['status'],'already_registered')
    def test_cached_changes_and_foreign_marketplace_are_not_overwritten(self):
        bundle=self.bundle(6);meta=json.loads((bundle/'host-registration.json').read_text())
        other=self.bundle(6,'foreign')
        registration.cli(self.codex,self.home,'plugin','marketplace','add',str(other))
        before=(self.home/'config.toml').read_bytes()
        with self.assertRaisesRegex(registration.RegistrationError,'marketplace_conflict'):registration.register(bundle,self.codex,self.home)
        self.assertEqual((self.home/'config.toml').read_bytes(),before)
        registration.register(other,self.codex,self.home)
        cached=self.home/'plugins/cache'/meta['marketplace']/meta['plugin']/meta['version']/'skills/luda/SKILL.md'
        cached.write_text('preserve user change')
        with self.assertRaisesRegex(registration.RegistrationError,'cached_content_mismatch'):registration.register(other,self.codex,self.home)
        self.assertEqual(cached.read_text(),'preserve user change')
