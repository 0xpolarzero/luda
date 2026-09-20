"""Target-account access is a selection precondition, not a root import claim."""
import os
from pathlib import Path
import pwd
import tempfile
import unittest
from unittest.mock import patch
import test_installation as fixture

installer = fixture.installer
# Preserve real implementations before the shared fake-build fixture patches them.
real_check = installer.check_install_access
real_verify = installer.verify_desktop_access

class InstallPermissions(unittest.TestCase):
    setUp = fixture.Installation.setUp
    runner = fixture.Installation.runner

    def test_restrictive_umask_normalizes_only_new_artifacts(self):
        original = self.source/'skills/luda/SKILL.md'; original.chmod(0o600)
        peer=self.root/'private-user-file';peer.write_text('keep');peer.chmod(0o600)
        old=os.umask(0o077)
        try:
            result=installer.install(self.prefix,self.source,self.runner)
            self.assertEqual(os.umask(0o077),0o077)
        finally:os.umask(old)
        release=self.prefix/'current'
        for path in (self.prefix,self.prefix/'releases',release,release/'.venv',release/'skills/luda'):
            self.assertEqual(path.stat().st_mode&0o777,0o755)
        self.assertEqual((release/'skills/luda/SKILL.md').stat().st_mode&0o777,0o644)
        self.assertEqual(original.stat().st_mode&0o777,0o600)
        self.assertEqual(peer.stat().st_mode&0o777,0o600)
        installer.verify_desktop_access.assert_called_once_with(self.prefix/'releases'/result['release'],'silo-desktop')

    def test_access_failure_preserves_selected_release_and_cleans_new_one(self):
        first=installer.install(self.prefix,self.source,self.runner)
        (self.source/'src/file.py').write_text('new')
        installer.verify_desktop_access.side_effect=installer.InstallError('unreadable')
        with self.assertRaises(installer.InstallError):installer.install(self.prefix,self.source,self.runner)
        self.assertEqual((self.prefix/'current').readlink().name,first['release'])
        self.assertEqual(len(list((self.prefix/'releases').iterdir())),1)

    def test_existing_prefix_modes_not_relaxed(self):
        self.prefix.mkdir(mode=0o700)
        with installer.locked(self.prefix):pass
        self.assertEqual(self.prefix.stat().st_mode&0o777,0o700)

    def test_reuse_and_rollback_probe_account_again(self):
        first=installer.install(self.prefix,self.source,self.runner)
        installer.verify_desktop_access.reset_mock()
        installer.install(self.prefix,self.source,self.runner)
        installer.rollback(self.prefix,first['release'])
        self.assertEqual(installer.verify_desktop_access.call_count,2)

    def test_preflight_failure_has_no_mutation(self):
        installer.check_install_access.side_effect=installer.InstallError('inaccessible')
        with self.assertRaises(installer.InstallError):installer.install(self.prefix,self.source,self.runner)
        self.assertFalse(self.prefix.exists());self.assertFalse(self.commands)

    def test_mode_normalization_does_not_follow_symlink(self):
        release=self.root/'owned';release.mkdir()
        external=self.root/'external';external.mkdir(mode=0o700)
        secret=external/'keep';secret.write_text('keep');secret.chmod(0o600)
        (release/'link').symlink_to(external,target_is_directory=True)
        installer.normalize_new_release(release)
        self.assertEqual(external.stat().st_mode&0o777,0o700)
        self.assertEqual(secret.stat().st_mode&0o777,0o600)

    @unittest.skipUnless(os.getuid()==0,'Requires root-to-desktop account access proof')
    def test_actual_target_account_refuses_inaccessible_existing_ancestor(self):
        try:pwd.getpwnam('silo-desktop')
        except KeyError:self.skipTest('No desktop account')
        self.root.chmod(0o700)
        with self.assertRaises(installer.InstallError):real_check(self.prefix,'silo-desktop')
        self.assertFalse(self.prefix.exists())
        self.assertEqual(self.root.stat().st_mode&0o777,0o700)

    def test_probe_cannot_import_source_instead_of_installed_package(self):
        # Real isolated Python with no installed luda cannot pass on a checkout.
        release=self.root/'probe';(release/'.venv/bin').mkdir(parents=True)
        import sys
        (release/'.venv/bin/python').symlink_to(Path(sys.executable).resolve())
        with self.assertRaises(installer.InstallError):
            real_verify(release,pwd.getpwuid(os.getuid()).pw_name)
