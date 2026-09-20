import asyncio
from contextlib import contextmanager, nullcontext
import json
import os
import sys
import threading
import unittest
from unittest.mock import Mock, patch

from luda import server, session_reconnect as reconnect
from luda.common import DesktopError, environment_scope, operation_scope, run, subprocess_environment


class Candidate:
    def __init__(self, environment=None):
        self.environment = environment or {'DISPLAY':':old','DBUS_SESSION_BUS_ADDRESS':'unix:path=/old'}
        self.closed = False
        self.control = Mock()
        self.control.status.return_value = {'paused':True}
        self.native = Mock(root=1)
        self.native.geometry.return_value = {'width':100,'height':80}
        self.locked = False
    @contextmanager
    def transaction(self):
        if self.locked: raise DesktopError('BUSY','Peer owns display.')
        self.locked = True
        try: yield
        finally:self.locked = False
    def display(self):return self.native
    def close(self):self.closed=True


class ReconnectTests(unittest.TestCase):
    def setUp(self):
        self.selected={'pid':42,'start':'123','environment':{'DISPLAY':':new','DBUS_SESSION_BUS_ADDRESS':'unix:path=/new'}}
        self.old=Candidate()
        self.new=Candidate(self.selected['environment'])
        self.stack=[]
        for name,value in [('select_session',self.selected),('_unchanged',None),('run',b'bus-id')]:
            p=patch.object(reconnect,name,return_value=value);self.stack.append(p);p.start();self.addCleanup(p.stop)
    def test_environment_context_is_immutable_and_restores(self):
        original=os.environ.get('LUDA_RECONNECT_ORACLE')
        env=dict(os.environ,LUDA_RECONNECT_ORACLE='candidate')
        with environment_scope(env):
            env['LUDA_RECONNECT_ORACLE']='changed-source'
            self.assertEqual(run([sys.executable,'-c','import os;print(os.environ["LUDA_RECONNECT_ORACLE"])']).strip(),b'candidate')
            with self.assertRaises(TypeError):subprocess_environment()['x']='y'
            with environment_scope(dict(env,LUDA_RECONNECT_ORACLE='nested')):
                self.assertEqual(subprocess_environment()['LUDA_RECONNECT_ORACLE'],'nested')
            self.assertEqual(subprocess_environment()['LUDA_RECONNECT_ORACLE'],'candidate')
        self.assertIsNone(subprocess_environment())
        self.assertEqual(os.environ.get('LUDA_RECONNECT_ORACLE'),original)
    def test_success_retains_pause_and_locks_during_swap(self):
        with reconnect.prepare_reconnect(self.old,None,lambda **kw:self.new) as (new,result):
            self.assertTrue(self.old.locked and new.locked)
            self.assertEqual(subprocess_environment()['DISPLAY'],':new')
            self.assertTrue(result['control']['paused'])
        self.assertFalse(self.old.closed or self.new.closed)
        self.assertFalse(self.old.locked or self.new.locked)
    def test_bus_failure_preserves_old_and_closes_candidate(self):
        reconnect.run.side_effect=DesktopError('COMMAND_FAILED','bus unavailable')
        with self.assertRaises(DesktopError):
            with reconnect.prepare_reconnect(self.old,None,lambda **kw:self.new):self.fail('must not swap')
        self.assertFalse(self.old.closed)
        self.assertTrue(self.new.closed)
    def test_cancel_preserves_old(self):
        event=threading.Event();event.set()
        with operation_scope(cancelled=event),self.assertRaises(DesktopError) as caught:
            with reconnect.prepare_reconnect(self.old,None,lambda **kw:self.new):self.fail()
        self.assertEqual(caught.exception.code,'CANCELLED')
        self.assertFalse(self.old.closed)
        self.assertTrue(self.new.closed)
    def test_peer_busy_preserves_old(self):
        self.new.locked=True
        with self.assertRaises(DesktopError) as caught:
            with reconnect.prepare_reconnect(self.old,None,lambda **kw:self.new):self.fail()
        self.assertEqual(caught.exception.code,'BUSY')
        self.assertFalse(self.old.closed)
    def test_same_display_does_not_double_acquire_peer_lock(self):
        self.old.environment=self.new.environment
        with reconnect.prepare_reconnect(self.old,None,lambda **kw:self.new):
            self.assertTrue(self.old.locked)
            self.assertFalse(self.new.locked)
    def test_server_success_swaps_then_closes(self):
        with patch.object(server,'backend',self.old),patch.object(server,'Desktop',return_value=self.new):
            response=server.execute('reconnect',42)
            self.assertFalse(response.isError,response)
            self.assertIs(server.backend,self.new)
            self.assertTrue(self.old.closed)
            self.assertFalse(self.new.closed)
    def test_repeated_reconnect_unregisters_closed_backends(self):
        registered=set()
        def register(callback):registered.add(callback)
        def unregister(callback):registered.discard(callback)
        with patch.object(server,'backend',self.old),patch.object(server.atexit,'register',side_effect=register),patch.object(server.atexit,'unregister',side_effect=unregister):
            registered.add(self.old.close)
            for _ in range(12):
                candidate=Candidate(self.selected['environment'])
                with patch.object(server,'Desktop',return_value=candidate):
                    self.assertFalse(server.execute('reconnect',42).isError)
                self.assertEqual(registered,{candidate.close})
            self.assertTrue(self.old.closed)

    def test_closed_backend_discards_cached_targets(self):
        from luda.desktop import Desktop
        desktop=Desktop()
        desktop.snapshots['private-image']={'image':'private'}
        desktop.elements['field']={'text':'private'}
        desktop.windows['window']={'title':'private'}
        desktop.close()
        self.assertEqual((desktop.snapshots,desktop.elements,desktop.windows),({},{},{}))

    def test_server_failed_probe_keeps_backend(self):
        reconnect.run.side_effect=DesktopError('COMMAND_FAILED','bad bus')
        with patch.object(server,'backend',self.old),patch.object(server,'Desktop',return_value=self.new):
            response=server.execute('reconnect',42)
            self.assertTrue(response.isError)
            self.assertIs(server.backend,self.old)
            self.assertFalse(self.old.closed)
    def test_busy_gate_rejects_without_discovery(self):
        with server._operation_gate:
            response=server.execute('reconnect',42)
            status=asyncio.run(server.desktop_status())
        self.assertEqual(json.loads(response.content[0].text)['code'],'BUSY')
        self.assertFalse(status.isError)
        reconnect.select_session.assert_not_called()


class SessionSelectionTests(unittest.TestCase):
    def test_invalid_pid(self):
        for pid in [True,0,-1,'42',1.1]:
            with self.subTest(pid=pid),self.assertRaises(DesktopError) as caught:reconnect.select_session(pid)
            self.assertEqual(caught.exception.code,'INVALID_ARGUMENT')
    def test_missing_or_foreign_session(self):
        with patch.object(reconnect,'_session',return_value=None),self.assertRaises(DesktopError) as caught:reconnect.select_session(42)
        self.assertEqual(caught.exception.code,'SESSION_NOT_FOUND')
    def test_ambiguity_lists_only_pid(self):
        with patch.object(reconnect.Path,'iterdir',return_value=[reconnect.Path('/proc/41'),reconnect.Path('/proc/42')]),patch.object(reconnect,'_session',side_effect=lambda pid,uid:{'pid':pid,'environment':{'SECRET':'never return'}}),self.assertRaises(DesktopError) as caught:reconnect.select_session()
        self.assertEqual(caught.exception.code,'SESSION_AMBIGUOUS')
        self.assertEqual(caught.exception.details,{'candidate_count':2,'session_pids':[41,42]})
    def test_changed_process_identity_rejected(self):
        selected={'pid':42,'start':'a','environment':{}}
        with patch.object(reconnect,'_session',return_value={**selected,'start':'b'}),self.assertRaises(DesktopError) as caught:reconnect._unchanged(selected)
        self.assertEqual(caught.exception.code,'SESSION_CHANGED')


if __name__=='__main__':unittest.main()
