import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import sys
import tempfile
import unittest
from unittest.mock import patch
from luda import managed_browser as browser
import test_installation as fixture
installer=fixture.installer


class BrowserSelection(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.path=self.root/'chromium'
        data=bytearray(32);data[:6]=b'\x7fELF\x02\x01';data[18:20]={'x86_64':62,'aarch64':183}[platform.machine()].to_bytes(2,'little')
        self.path.write_bytes(data);self.path.chmod(0o755)
        self.value=dict(schema_version=1,executable=str(self.path),sha256=hashlib.sha256(data).hexdigest(),version='1.2.3.4',architecture=platform.machine())
    def test_hash_and_arch_checked_before_executing(self):
        with patch.object(browser,'bounded_version',return_value='1.2.3.4') as probe:
            self.assertEqual(browser.verify(self.value),self.value)
            self.path.write_bytes(b'replacement')
            with self.assertRaises(ValueError):browser.verify(self.value)
            self.assertEqual(probe.call_count,1)
    def test_bad_schema_symlink_version_and_modes(self):
        for bad in ({**self.value,'schema_version':True},{**self.value,'version':'latest'},{**self.value,'architecture':'unknown'},{**self.value,'extra':'x'}):
            with self.assertRaises(ValueError):browser.normalize(bad)
        alias=self.root/'alias';alias.symlink_to(self.path)
        with self.assertRaises(ValueError):browser.normalize({**self.value,'executable':str(alias)})
        self.path.chmod(0o777)
        with self.assertRaises(ValueError):browser.verify(self.value)
        self.path.chmod(0o755)
        with patch.object(browser,'bounded_version',return_value='9.9.9.9'),self.assertRaises(ValueError):browser.verify(self.value)
    def test_absent_config_and_untrusted_config(self):
        self.assertIsNone(browser.selected(self.root))
        config=self.root/browser.CONFIG_NAME;config.write_text(json.dumps(self.value));config.chmod(0o666)
        with self.assertRaises(ValueError):browser.selected(self.root)
    def test_bounded_probe_cleans_successful_parent_background_child(self):
        self.root.chmod(0o755)
        script=self.root/'probe';marker=self.root/'late'
        # Run this shell fixture only as current nonroot user, or selected nobody;
        # private marker directory is explicitly writable by that test account.
        self.root.chmod(0o777)
        script.write_text('#!/bin/sh\n(sleep 1; touch "'+str(marker)+'") >/dev/null 2>&1 &\necho "Chromium 1.2.3.4"\n');script.chmod(0o755)
        self.assertEqual(browser.bounded_version(str(script),'nobody'),'1.2.3.4')
        import time;time.sleep(1.1);self.assertFalse(marker.exists())
        script.write_text('#!/bin/sh\nyes oversized\n')
        with self.assertRaisesRegex(ValueError,'limit'):browser.bounded_version(str(script),'nobody')
        script.write_text('#!/bin/sh\nsleep 20\n')
        start=time.monotonic()
        with self.assertRaisesRegex(ValueError,'timed out'):browser.bounded_version(str(script),'nobody')
        self.assertLess(time.monotonic()-start,5)


class ManagedInstallerBrowser(unittest.TestCase):
    setUp=fixture.Installation.setUp
    runner=fixture.Installation.runner
    def test_optional_identity_repeat_failure_and_rollback(self):
        config=self.root/'browser.json';config.write_text('{}')
        value=dict(schema_version=1,executable='/trusted/chrome',sha256='a'*64,version='1.2.3.4',architecture=platform.machine())
        (self.source/'requirements-browser.lock').write_text('optional locked deps')
        base=installer.install(self.prefix,self.source,self.runner)
        with patch.object(installer,'read_browser_config',return_value=value),patch.object(installer,'verify_browser',return_value=value),patch.object(installer,'selected_browser',return_value=value):
            enabled=installer.install(self.prefix,self.source,self.runner,browser_config=config)
            self.assertNotEqual(base['release'],enabled['release'])
            self.assertTrue(any('requirements-browser.lock' in str(arg) for cmd in self.commands for arg in cmd))
            self.assertEqual(json.loads((self.prefix/'current/.venv/luda-browser.json').read_text()),value)
            self.assertEqual(installer.install(self.prefix,self.source,self.runner,browser_config=config)['status'],'already_installed')
            installer.rollback(self.prefix,base['release'])
            self.assertFalse((self.prefix/'current/.venv/luda-browser.json').exists())
        with patch.object(installer,'selected_browser',side_effect=ValueError('changed')),self.assertRaises(installer.InstallError):installer.rollback(self.prefix,enabled['release'])
        self.assertEqual((self.prefix/'current').resolve().name,base['release'])
        with patch.object(installer,'read_browser_config',return_value=value),patch.object(installer,'verify_browser',side_effect=ValueError('bad hash')),self.assertRaises(ValueError):installer.install(self.prefix,self.source,self.runner,browser_config=config)
        self.assertEqual((self.prefix/'current').resolve().name,base['release'])
