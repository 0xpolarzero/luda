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
