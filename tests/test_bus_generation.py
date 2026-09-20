import ctypes
from types import SimpleNamespace as N
import unittest
from unittest.mock import Mock,patch
from test_semantic import load_worker
w=load_worker()

class Generation(unittest.TestCase):
 def native(self,guid=b'a'*32,connected=1,connection=123,pointer=True):
  self.buffer=ctypes.create_string_buffer(guid)
  self.atspi=N(atspi_get_a11y_bus=Mock(return_value=connection))
  self.dbus=N(dbus_connection_get_is_connected=Mock(return_value=connected),dbus_connection_get_server_id=Mock(return_value=ctypes.addressof(self.buffer) if pointer else None),dbus_free=Mock())
  with patch('ctypes.CDLL',side_effect=[self.atspi,self.dbus]):return w._native_bus_generation()
 def test_authenticated_guid_reads_exact_connection_and_frees_string(self):
  self.assertEqual(self.native(),'a'*32);self.dbus.dbus_connection_get_server_id.assert_called_once_with(123);self.dbus.dbus_free.assert_called_once()
 def test_missing_connection_or_guid_refused(self):
  for args in ({'connection':None},{'connected':0},{'pointer':False}):
   with self.subTest(args=args),self.assertRaises(w.BusIdentityUnavailable):self.native(**args)
 def test_malformed_guid_refused_and_freed(self):
  for guid in (b'',b'not-a-guid',b'g'*32,b'a'*33,b'\xff'*32):
   with self.subTest(guid=guid),self.assertRaises(w.BusIdentityUnavailable):self.native(guid)
   self.dbus.dbus_free.assert_called_once()
 def test_missing_library_diagnostic_is_sanitized(self):
  with patch('ctypes.CDLL',side_effect=OSError('private value')):
   with self.assertRaises(w.BusIdentityUnavailable) as caught:w._native_bus_generation()
  self.assertNotIn('private',str(caught.exception))
 def test_changed_or_missing_generation_refuses_before_traversal(self):
  for guid in (None,'b'*32):
   with patch.object(w,'candidates') as candidates:
    result=w.dispatch({'op':'invoke','pid':42,'target':{'root_bus_guid':guid}})
   self.assertEqual(result['error'],'STALE_TARGET');self.assertEqual(result['effect'],'none');candidates.assert_not_called()
 def test_unavailable_generation_never_invokes_action(self):
  with patch.object(w,'bus_generation',side_effect=w.BusIdentityUnavailable),patch.object(w,'semantic') as action:
   result=w.dispatch({'op':'invoke','pid':42,'target':{'root_bus_guid':'a'*32}})
  self.assertEqual(result['error'],'ACCESSIBILITY_UNAVAILABLE');self.assertEqual(result['effect'],'none');action.assert_not_called()
 def test_generation_changes_during_target_resolution_refuses(self):
  node=N(path='/button');current=dict(role='push button',name='name',start='1',states=['enabled','showing'],protected=False)
  target=dict(current,path='/button',root_path='/root',root_bus_guid='a'*32)
  with patch.object(w,'bus_generation',side_effect=['a'*32,'b'*32]),patch.object(w,'candidates',return_value=[(node,0)]),patch.object(w,'describe',return_value=current),patch.object(w,'semantic') as action:
   result=w.dispatch(dict(op='invoke',pid=42,target=target))
  self.assertEqual(result['error'],'STALE_TARGET');self.assertEqual(result['effect'],'none');action.assert_not_called()

if __name__=='__main__':unittest.main()
