import fcntl
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

from luda.admission import Admission, MAX_CLIENTS, MAX_BYTES
from luda.common import DesktopError, operation_scope
from luda.timing import elapsed_time


class AdmissionTests(unittest.TestCase):
    def setUp(self):
        self.directory=tempfile.TemporaryDirectory();self.addCleanup(self.directory.cleanup)
        self.path=Path(self.directory.name)
        self.clients=[Admission(self.path,'display') for _ in range(4)]
        self.fds=[os.open(self.path/'display.lock',os.O_CREAT|os.O_RDWR,0o600) for _ in range(4)]
        for fd in self.fds:self.addCleanup(os.close,fd)
    def busy(self,index,position=None):
        with self.assertRaises(DesktopError) as error:self.clients[index].acquire(self.fds[index])
        self.assertEqual(error.exception.code,'BUSY')
        self.assertEqual(error.exception.effect,'none')
        if position is not None:self.assertEqual(error.exception.details['queue_position'],position)
        return error.exception
    def state(self):return json.loads((self.path/'display.admission.json').read_text())
    def write(self,state):
        path=self.path/'display.admission.json';path.write_text(json.dumps(state));path.chmod(0o600)
    def test_fast_previous_owner_cannot_overtake_fifo(self):
        self.clients[0].acquire(self.fds[0])
        for index in (1,2,3):self.busy(index,index)
        self.clients[0].release(self.fds[0])
        for head in (1,2,3):
            for _ in range(10):self.busy(0)
            self.clients[head].acquire(self.fds[head])
            self.clients[head].release(self.fds[head])
        self.clients[0].acquire(self.fds[0]);self.clients[0].release(self.fds[0])
        self.assertEqual(self.state()['queue'],[])
    def test_idle_head_expires(self):
        self.clients[0].acquire(self.fds[0]);self.busy(1,1)
        self.clients[0].release(self.fds[0])
        with patch('luda.admission.elapsed_time',return_value=elapsed_time()+3):
            self.clients[2].acquire(self.fds[2]);self.clients[2].release(self.fds[2])
        self.assertEqual(self.state()['queue'],[])
    def test_retry_renews_priority_without_reordering(self):
        self.clients[0].acquire(self.fds[0]);self.busy(1,1);self.busy(2,2)
        before=self.state()['queue']
        with patch('luda.admission.elapsed_time',return_value=elapsed_time()+1):self.busy(2,2)
        after=self.state()['queue']
        self.assertEqual([x['nonce'] for x in before],[x['nonce'] for x in after])
        self.assertGreater(after[1]['expires'],before[1]['expires'])
        self.clients[0].release(self.fds[0])
    def test_dead_pid_and_reused_pid_are_removed(self):
        self.clients[0].acquire(self.fds[0]);self.busy(1,1);self.busy(2,2)
        data=self.state();data['queue'][0]['pid']=2147483647;data['queue'][1]['start']='0';self.write(data)
        self.clients[0].release(self.fds[0])
        self.clients[3].acquire(self.fds[3]);self.clients[3].release(self.fds[3])
        self.assertEqual(self.state()['queue'],[])
    def test_cancel_removes_pending_ticket(self):
        self.clients[0].acquire(self.fds[0]);self.busy(1,1)
        event=threading.Event();event.set()
        with operation_scope(cancelled=event),self.assertRaises(DesktopError) as error:self.clients[1].acquire(self.fds[1])
        self.assertEqual(error.exception.code,'CANCELLED')
        self.assertEqual(self.state()['queue'],[])
        self.clients[0].release(self.fds[0])
    def test_cancellation_after_lock_releases_display_and_ticket(self):
        with patch('luda.admission.checkpoint',side_effect=[None,None,DesktopError('CANCELLED','test')]),self.assertRaises(DesktopError):self.clients[0].acquire(self.fds[0])
        self.clients[1].acquire(self.fds[1]);self.clients[1].release(self.fds[1])
        self.assertEqual(self.state()['queue'],[])
    def test_failed_state_commit_releases_display(self):
        with patch.object(self.clients[0],'_write',side_effect=OSError('test')),self.assertRaises(DesktopError):self.clients[0].acquire(self.fds[0])
        self.clients[1].acquire(self.fds[1]);self.clients[1].release(self.fds[1])
    def test_queue_capacity_is_explicit_and_bounded(self):
        self.clients[0].acquire(self.fds[0]);self.busy(1)
        data=self.state();template=data['queue'][0]
        data['queue']=[dict(template,nonce=f'{i:032x}') for i in range(MAX_CLIENTS)];self.write(data)
        error=self.busy(2)
        self.assertFalse(error.details['queued'])
        self.assertEqual(len(self.state()['queue']),MAX_CLIENTS)
        self.clients[0].release(self.fds[0])
    def test_old_boot_tickets_are_discarded(self):
        self.clients[0].acquire(self.fds[0]);self.busy(1)
        data=self.state();data['boot']='00000000-0000-0000-0000-000000000000';self.write(data)
        self.clients[0].release(self.fds[0]);self.clients[2].acquire(self.fds[2]);self.clients[2].release(self.fds[2])
    def test_coordinator_contention_is_nonblocking(self):
        directory,lock=self.clients[0]._open()
        try:
            error=self.busy(1);self.assertFalse(error.details['queued'])
            self.assertFalse(self.clients[1].cancel())
        finally:os.close(lock);os.close(directory)
    def test_unsafe_registry_refused_without_touching_target(self):
        state=self.path/'display.admission.json';victim=self.path/'victim';victim.write_text('preserve')
        for kind in ('symlink','hardlink','world-readable','oversized','malformed','fifo'):
            with self.subTest(kind=kind):
                state.unlink(missing_ok=True)
                if kind=='symlink':state.symlink_to(victim)
                elif kind=='hardlink':os.link(victim,state)
                elif kind=='fifo':os.mkfifo(state,0o600)
                else:state.write_text('x'*(MAX_BYTES+1) if kind=='oversized' else '{}');state.chmod(0o644 if kind=='world-readable' else 0o600)
                with self.assertRaises(DesktopError) as error:self.clients[0].acquire(self.fds[0])
                self.assertEqual(error.exception.code,'ADMISSION_UNAVAILABLE')
                self.assertEqual(victim.read_text(),'preserve')
    def test_unsafe_lock_and_directory_refused(self):
        lock=self.path/'display.admission.lock';lock.symlink_to(self.path/'display.lock')
        with self.assertRaises(DesktopError):self.clients[0].acquire(self.fds[0])
        lock.unlink();self.path.chmod(0o755)
        with self.assertRaises(DesktopError):self.clients[0].acquire(self.fds[0])
        self.path.chmod(0o700)
    def test_no_operation_arguments_are_stored(self):
        self.clients[0].acquire(self.fds[0]);self.busy(1)
        self.assertEqual(set(self.state()['queue'][0]),{'nonce','pid','start','expires'})
        self.clients[0].release(self.fds[0])


class MultiprocessAdmissionTests(unittest.TestCase):
    SCRIPT = r"""
import json,os,sys
from pathlib import Path
from luda.admission import Admission
from luda.common import DesktopError
root=Path(sys.argv[1]);a=Admission(root,'display')
fd=os.open(root/'display.lock',os.O_CREAT|os.O_RDWR,0o600)
for line in sys.stdin:
 command=line.strip()
 try:
  if command=='acquire':a.acquire(fd)
  elif command=='release':a.release(fd)
  else:break
  print(json.dumps({'ok':True}),flush=True)
 except DesktopError as e:print(json.dumps({'code':e.code,**e.details}),flush=True)
"""
    def test_real_process_fifo_and_crash_recovery(self):
        import select
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);owner=Admission(root,'display')
            fd=os.open(root/'display.lock',os.O_CREAT|os.O_RDWR,0o600)
            children=[subprocess.Popen([sys.executable,'-c',self.SCRIPT,directory],stdin=subprocess.PIPE,stdout=subprocess.PIPE,text=True) for _ in range(3)]
            def ask(child,command):
                child.stdin.write(command+'\n');child.stdin.flush()
                self.assertTrue(select.select([child.stdout],[],[],3)[0],'Admission worker did not answer')
                return json.loads(child.stdout.readline())
            try:
                owner.acquire(fd)
                for index,child in enumerate(children):
                    result=ask(child,'acquire')
                    self.assertEqual(result['code'],'BUSY')
                    self.assertEqual(result['queue_position'],index+1)
                owner.release(fd)
                for child in children:
                    for _ in range(10):
                        with self.assertRaises(DesktopError) as error:owner.acquire(fd)
                        self.assertEqual(error.exception.code,'BUSY')
                    self.assertTrue(ask(child,'acquire')['ok'])
                    # A second process never enters while the admitted owner holds.
                    with self.assertRaises(DesktopError):owner.acquire(fd)
                    self.assertTrue(ask(child,'release')['ok'])
                owner.acquire(fd);owner.release(fd)
                self.assertTrue(ask(children[0],'acquire')['ok'])
                with self.assertRaises(DesktopError):owner.acquire(fd)
                children[0].kill();children[0].wait(timeout=2)
                owner.acquire(fd);owner.release(fd)
                owner.acquire(fd)
                self.assertEqual(ask(children[1],'acquire')['code'],'BUSY')
                children[1].kill();children[1].wait(timeout=2)
                owner.release(fd)
                owner.acquire(fd);owner.release(fd)
            finally:
                os.close(fd)
                for child in children:
                    if child.poll() is None:child.kill();child.wait(timeout=2)
                    child.stdin.close();child.stdout.close()


if __name__=='__main__':unittest.main()
