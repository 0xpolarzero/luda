import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch
from luda.common import DesktopError
spec=importlib.util.spec_from_file_location('workspace_gap_probe',Path(__file__).parent/'evidence/workspace-observation-gap/probe.py')
probe=importlib.util.module_from_spec(spec);spec.loader.exec_module(probe)

class WorkspaceSnapshots(unittest.TestCase):
 def test_verified_switch_and_return_expire_old_coordinates(self):
  d=probe.Driver()
  with patch('luda.interaction.run',side_effect=lambda cmd,**kw:setattr(d,'workspace',int(cmd[-1]))):
   result=d.switch_workspace(1)
   self.assertEqual(result['effect'],'verified');self.assertEqual(result['screenshot_ids_invalidated'],1)
   d.switch_workspace(0)
  with self.assertRaises(DesktopError) as caught:d._interaction_point('sticky','before',20,20)
  self.assertEqual(caught.exception.code,'STALE_OBSERVATION')
 def test_current_workspace_request_is_dispatched_and_expires(self):
  d=probe.Driver()
  with patch('luda.interaction.run') as run:result=d.switch_workspace(0)
  run.assert_called_once();self.assertEqual(result['screenshot_ids_invalidated'],1);self.assertFalse(d.snapshots)
 def test_uncertain_dispatch_expires_before_backend_call(self):
  d=probe.Driver()
  def dispatch(*args,**kwargs):
   self.assertFalse(d.snapshots)
   raise DesktopError('TIMEOUT','uncertain switch',effect='uncertain')
  with patch('luda.interaction.run',side_effect=dispatch),self.assertRaises(DesktopError):d.switch_workspace(1)
  self.assertFalse(d.snapshots)
 def test_invalid_workspace_preserves_snapshot_without_dispatch(self):
  for invalid in (True,-1,2,'1'):
   d=probe.Driver()
   with patch('luda.interaction.run') as run,self.assertRaises(DesktopError):d.switch_workspace(invalid)
   run.assert_not_called();self.assertIn('before',d.snapshots)
