import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
from luda.desktop import Desktop
from luda.common import DesktopError,environment_scope


class DoctorEnvironment(unittest.TestCase):
    def test_selected_backend_path_drives_dependency_readiness(self):
        with tempfile.TemporaryDirectory() as directory:
            for name in ('xdotool','wmctrl','scrot','xclip','xprop'):
                path=Path(directory)/name;path.write_text('#!/bin/sh\nexit 0\n');path.chmod(0o700)
            d=Desktop(dict(os.environ,PATH=directory,DISPLAY=':selected',DBUS_SESSION_BUS_ADDRESS='selected'))
            self.addCleanup(d.close);d.x=Mock();d.x.root=1;d.x.geometry.return_value={'width':100,'height':100}
            d.x.topology.return_value={'root':d.x.geometry.return_value,'randr':{'version':[1,6],'monitors':[],'crtcs':[]}}
            with patch.dict(os.environ,PATH='/nonexistent'),patch('luda.desktop.run',return_value=b'1'),patch('luda.desktop.session_state',return_value={'input_ready':None}),patch('luda.desktop.keyboard_capabilities',return_value={'available':True}):
                self.assertTrue(d.doctor()['ready'])
                (Path(directory)/'scrot').unlink()
                result=d.doctor();self.assertFalse(result['ready']);self.assertFalse(result['dependencies']['scrot'])

    def test_missing_enumerator_diagnostic_matches_real_precondition(self):
        with tempfile.TemporaryDirectory() as directory:
            d=Desktop(dict(os.environ,PATH=directory));self.addCleanup(d.close)
            d.x=Mock();d.x.geometry.return_value={'width':100,'height':100}
            d.x.topology.return_value={'root':d.x.geometry.return_value,'randr':{'version':[1,6],'monitors':[],'crtcs':[]}}
            with patch('luda.desktop.run',return_value=b'1'),patch('luda.desktop.session_state',return_value={'input_ready':None}),patch('luda.desktop.keyboard_capabilities',return_value={'available':True}):
                result=d.doctor()
            self.assertFalse(result['dependencies']['wmctrl'])
            self.assertEqual(result['capabilities']['accessibility_read'],'unavailable')
            # Exercise the real command boundary, not a simulated provider failure.
            with environment_scope(d.environment),self.assertRaises(DesktopError) as raised:
                d.list_windows()
            self.assertEqual(raised.exception.code,'DEPENDENCY_MISSING')
            self.assertEqual(raised.exception.effect,'none')

    def test_malformed_provider_count_is_redacted_and_not_ready(self):
        d=Desktop();self.addCleanup(d.close);d.x=Mock();d.x.geometry.return_value={}
        d.x.topology.return_value={'root':d.x.geometry.return_value,'randr':{'version':[1,6],'monitors':[],'crtcs':[]}}
        for output in (b'synthetic-private-provider-output',b'-1'):
            with patch('luda.desktop.run',return_value=output),patch('luda.desktop.session_state',return_value={'input_ready':None}),patch('luda.desktop.keyboard_capabilities',return_value={'available':True}):
                result=d.doctor()
                self.assertFalse(result['accessibility_available']);self.assertFalse(result['ready'])
                self.assertNotIn(output.decode(),result['accessibility_error'])
