"""The documented managed diagnostic uses the installed canonical CLI."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec=importlib.util.spec_from_file_location('managed_doctor_installer',Path(__file__).resolve().parents[1]/'scripts/manage_install.py')
installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)

class ManagedDoctor(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory();self.addCleanup(temp.cleanup)
        self.prefix=Path(temp.name)/'owned prefix'
        self.release=self.prefix/'releases/selected';self.release.mkdir(parents=True)
        (self.prefix/'current').symlink_to('releases/selected')

    def test_session_boundary_immutable_paths_and_identity_payload(self):
        payload={'ready':True,'versions':{'driver_version':'test','tool_schema':{'sha256':'a'*64},'bundled_skill':{'status':'identified','sha256':'b'*64}}}
        def run(command,**kwargs):
            # A concurrent selection switch must not change either command path.
            (self.prefix/'current').unlink();(self.prefix/'current').symlink_to('releases/other')
            self.assertEqual(command,[str(self.release/'.venv/bin/luda-session'),'--user','chosen-desktop','--',str(self.release/'.venv/bin/luda'),'doctor'])
            self.assertEqual(kwargs,{'capture_output':True,'text':True,'timeout':20})
            return subprocess.CompletedProcess(command,0,json.dumps(payload),'')
        with patch.object(installer.subprocess,'run',side_effect=run):
            self.assertEqual(installer.doctor(self.prefix,'chosen-desktop'),payload)

    def test_not_ready_cli_exit_is_failure_with_diagnostic(self):
        payload=json.dumps({'ready':False,'accessibility_available':False})
        with patch.object(installer.subprocess,'run',return_value=subprocess.CompletedProcess([],1,payload,'')):
            with self.assertRaisesRegex(installer.InstallError,'Desktop readiness failed:.*accessibility_available'):
                installer.doctor(self.prefix,'chosen-desktop')

    def test_session_failure_stderr_is_preserved(self):
        with patch.object(installer.subprocess,'run',return_value=subprocess.CompletedProcess([],1,'','No matching XFCE session')):
            with self.assertRaisesRegex(installer.InstallError,'No matching XFCE session'):
                installer.doctor(self.prefix,'chosen-desktop')

    def test_missing_selection_does_not_launch(self):
        (self.prefix/'current').unlink()
        with patch.object(installer.subprocess,'run') as launch:
            with self.assertRaisesRegex(installer.InstallError,'No selected installation'):
                installer.doctor(self.prefix,'chosen-desktop')
            launch.assert_not_called()
