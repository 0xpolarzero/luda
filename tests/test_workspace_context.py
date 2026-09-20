import unittest
from unittest.mock import patch
from PIL import Image
from luda._x11_helper import _NativeX11
from luda.common import DesktopError
from luda.desktop import Desktop
import test_screenshot_limits

class WorkspaceContext(unittest.TestCase):
 def native(self,current,count=None,supported=None):
  x=_NativeX11.__new__(_NativeX11);x.root=1;x._property_atoms={'_NET_CURRENT_DESKTOP':99}
  values={'_NET_CURRENT_DESKTOP':current,'_NET_NUMBER_OF_DESKTOPS':count,'_NET_SUPPORTED':supported}
  x._property=lambda root,name,limit:values[name]
  return x
 def test_current_zero_is_available_not_unsupported(self):
  self.assertEqual(self.native((6,32,[0],0),(6,32,[2],0)).workspace_context(),{'status':'available','index':0,'count':2})
  self.assertEqual(self.native((6,32,[1],0)).workspace_context(),{'status':'available','index':1,'count':None})
  self.assertEqual(self.native(None).workspace_context(),{'status':'unsupported'})
  self.assertEqual(self.native(None,supported=(4,32,[88],0)).workspace_context(),{'status':'unsupported'})
 def test_advertised_missing_invalid_type_count_and_bound_refuse(self):
  cases=[self.native(None,supported=(4,32,[99],0)),self.native(None,supported=(6,32,[99],0)),self.native(None,supported=(4,32,[99],4))]
  for current in ((6,32,[],0),(6,32,[0,1],0),(6,32,[0],4),(31,32,[0],0),(6,8,[0],0),(6,32,[4096],0)):
   cases.append(self.native(current))
  for count in ((6,32,[0],0),(6,32,[1],0),(6,32,[4097],0),(31,8,b'x',0)):
   cases.append(self.native((6,32,[1],0),count))
  for x in cases:
   with self.subTest(x=x),self.assertRaises(DesktopError) as caught:x.workspace_context()
   self.assertEqual(caught.exception.code,'INVALID_PROPERTY')
 def test_workspace_change_during_capture_refuses_snapshot(self):
  fixture=test_screenshot_limits.ScreenshotLimitsTests();d=fixture.driver(100,100)
  try:
   d.x.topology.side_effect=[{'server_generation':'one','workspace':{'index':0}},{'server_generation':'one','workspace':{'index':1}}]
   def capture(argv,**kw):Image.new('RGB',(100,100)).save(argv[-1])
   with patch('luda.desktop.run',side_effect=capture),self.assertRaises(DesktopError) as caught:d.observe()
   self.assertEqual(caught.exception.code,'DESKTOP_CHANGED');self.assertFalse(d.snapshots)
  finally:fixture.doCleanups()
 def test_historical_template_survives_workspace_change_but_not_restart(self):
  from luda.timing import elapsed_time
  d=Desktop.__new__(Desktop);d.snapshots={'old':{'time':elapsed_time(),'png':b'fixture','topology':{'server_generation':'one','workspace':{'index':0}}}}
  class Display:
   generation='one'
   def topology(self):return {'server_generation':self.generation,'workspace':{'index':1}}
  x=Display();d.display=lambda:x
  self.assertIs(d.retained_snapshot('old',current_layout=False),d.snapshots['old'])
  x.generation='two'
  with self.assertRaises(DesktopError) as caught:d.retained_snapshot('old',current_layout=False)
  self.assertEqual(caught.exception.code,'STALE_OBSERVATION')
