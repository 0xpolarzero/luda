import unittest
from unittest.mock import Mock
from luda.desktop import Desktop
from luda.common import DesktopError
from luda.timing import elapsed_time
class BrowserInspectionFallbackTests(unittest.TestCase):
 def desktop(self):
  d=Desktop.__new__(Desktop);d.elements={};d.target_window=Mock(return_value={'pid':10,'start':'20','bounds':{},'frame_bounds':{},'title':'same'});d.browser=Mock(window_id='window');d.browser.inspect.side_effect=DesktopError('BROWSER_SCOPE_UNSUPPORTED','scope')
  d.ax=Mock(return_value={'nodes':[{'path':'/root','name':'App','role':'frame'},{'path':'/button','parent_path':'/root','name':'Continue','role':'push button'}],'available':True})
  return d
 def test_scope_refusal_preserves_native_node_identity_and_parent(self):
  d=self.desktop();v=d.inspect('window');self.assertEqual(v['owned_browser'],{'available':False,'code':'BROWSER_SCOPE_UNSUPPORTED'});self.assertEqual(v['text_fields'],[]);self.assertTrue(v['available']);self.assertEqual(len(v['nodes']),2)
  root,child=v['nodes'];self.assertEqual(child['parent_element_id'],root['element_id']);self.assertEqual(d.elements[child['element_id']]['node']['path'],'/button');self.assertEqual(d.elements[child['element_id']]['window_id'],'window')
 def test_native_error_is_not_replaced_by_empty_success(self):
  d=self.desktop();d.ax.side_effect=DesktopError('ACCESSIBILITY_UNAVAILABLE','native absent')
  with self.assertRaises(DesktopError) as e:d.inspect('window')
  self.assertEqual(e.exception.code,'ACCESSIBILITY_UNAVAILABLE')
 def test_cancellation_and_other_provider_errors_propagate(self):
  for code in ('CANCELLED','TIMEOUT','STALE_TARGET','BROWSER_OPERATION_FAILED'):
   with self.subTest(code=code):
    d=self.desktop();d.browser.inspect.side_effect=DesktopError(code,'fixed')
    with self.assertRaises(DesktopError) as e:d.inspect('window')
    self.assertEqual(e.exception.code,code);d.ax.assert_not_called()
 def test_cached_owned_mutation_keeps_original_provider_and_refusal(self):
  d=self.desktop();d.elements['old']={'time':elapsed_time(),'window_id':'window','provider':'owned_browser','browser_token':'private'};d.inspect('window');d.browser.element.side_effect=DesktopError('BROWSER_SCOPE_UNSUPPORTED','scope');d.ax.reset_mock()
  with self.assertRaises(DesktopError) as e:d.element('old','focus')
  self.assertEqual(e.exception.code,'BROWSER_SCOPE_UNSUPPORTED');d.ax.assert_not_called();d.browser.element.assert_called_once()
if __name__=='__main__':unittest.main()
