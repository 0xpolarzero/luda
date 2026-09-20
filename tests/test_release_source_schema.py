"""Malformed source metadata cannot escape staged bootstrap JSON or start work."""
import json
import os
from pathlib import Path
import pwd
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
import manage_install as installer
import bootstrap_guest as bootstrap

CASES={
    'missing-project':'[tool.fixture]\nvalue="SENSITIVE"\n',
    'project-string':'project="SENSITIVE"\n',
    'project-array':'project=["SENSITIVE"]\n',
    'missing-version':'[project]\nname="SENSITIVE"\n',
    'integer-version':'[project]\nversion=123\n',
    'boolean-version':'[project]\nversion=true\n',
    'array-version':'[project]\nversion=["SENSITIVE"]\n',
    'table-version':'[project.version]\nprivate="SENSITIVE"\n',
    'empty-version':'[project]\nversion=""\n',
    'unsafe-version':'[project]\nversion="../SENSITIVE"\n',
    'invalid-toml':'[project\nversion="SENSITIVE"\n',
}

class ReleaseSourceSchema(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.source=self.root/'source';self.prefix=self.root/'install';self.output=self.root/'bundle'
        for name in ('scripts/install.sh','scripts/manage_install.py','requirements.lock','build-requirements.lock','MANIFEST.in','skills/luda/SKILL.md'):
            path=self.source/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('fixture')
        self.metadata=self.source/'pyproject.toml'
        self.user=(next(account for account in pwd.getpwall() if account.pw_uid!=0) if os.getuid()==0 else pwd.getpwuid(os.getuid())).pw_name
    def test_schema_failures_are_install_errors_before_mutation(self):
        for name,text in CASES.items():
            with self.subTest(case=name):
                self.metadata.write_text(text);runner=Mock()
                with self.assertRaises(installer.InstallError) as caught:
                    installer.install(self.prefix,self.source,runner)
                self.assertNotIn('SENSITIVE',str(caught.exception));runner.assert_not_called();self.assertFalse(self.prefix.exists())
    def test_bootstrap_schema_errors_are_staged_and_do_not_start_children(self):
        for name,text in CASES.items():
            with self.subTest(case=name),patch.object(bootstrap,'desktop_status') as status,patch.object(bootstrap,'run_process') as child:
                self.metadata.write_text(text)
                result=bootstrap.bootstrap(self.source,self.prefix,self.output,self.user,skip_system=True)
                self.assertFalse(result['ok']);self.assertEqual(result['stage'],'validation');self.assertIs(result['installation_completed'],False)
                self.assertNotIn('SENSITIVE',json.dumps(result));status.assert_not_called();child.assert_not_called()
                self.assertFalse(self.prefix.exists());self.assertFalse(self.output.exists())
    def test_actual_cli_returns_one_redacted_json_object_for_shape_errors(self):
        for name in ('missing-project','missing-version','project-string','integer-version','table-version'):
            with self.subTest(case=name):
                self.metadata.write_text(CASES[name])
                result=subprocess.run([sys.executable,str(ROOT/'scripts/bootstrap_guest.py'),'--source',str(self.source),'--prefix',str(self.prefix),'--output',str(self.output),'--user',self.user,'--skip-system'],capture_output=True,text=True,timeout=5)
                self.assertEqual(result.returncode,1);payload=json.loads(result.stdout)
                self.assertEqual(payload['stage'],'validation');self.assertFalse(payload['installation_completed']);self.assertEqual(result.stderr,'')
                self.assertNotIn('SENSITIVE',result.stdout);self.assertFalse(self.prefix.exists());self.assertFalse(self.output.exists())
    def test_valid_string_version_still_hashes_source(self):
        self.metadata.write_text('[project]\nversion="1.2.3+fixture"\n')
        self.assertRegex(installer.release_identity(self.source),r'^1\.2\.3\+fixture-[0-9a-f]{16}$')
    def test_invalid_utf8_is_a_redacted_install_error(self):
        self.metadata.write_bytes(b'[project]\nversion="SENSITIVE\xff"')
        with self.assertRaises(installer.InstallError) as caught:installer.release_identity(self.source)
        self.assertNotIn('SENSITIVE',str(caught.exception))
