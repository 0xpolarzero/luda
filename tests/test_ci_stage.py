"""Actual Linux detached/stopped child cleanup; no installer, network or GUI."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest

ROOT=Path(__file__).resolve().parents[1]

@unittest.skipUnless(sys.platform=='linux' and hasattr(os,'pidfd_open'),'Linux pidfd/subreaper fixture')
class CiStage(unittest.TestCase):
    def test_timeout_and_success_reap_detached_stopped_child_preserve_peer(self):
        for mode in ('timeout','success'):
            with self.subTest(mode=mode),tempfile.TemporaryDirectory() as directory:
                root=Path(directory);pidfile=root/'child';marker=root/'late';receipt=root/'receipt.json'
                worker=root/'worker.py';worker.write_text('import os,signal,time\nfrom pathlib import Path\nos.setsid()\nsignal.signal(signal.SIGTERM,signal.SIG_IGN)\nPath('+repr(str(pidfile))+').write_text(str(os.getpid()))\nos.kill(os.getpid(),signal.SIGSTOP)\ntime.sleep(2)\nPath('+repr(str(marker))+').write_text("late")\n')
                parent=root/'parent.py';parent.write_text('import subprocess,sys,time\nfrom pathlib import Path\nsubprocess.Popen([sys.executable,'+repr(str(worker))+'])\nwhile not Path('+repr(str(pidfile))+').exists():time.sleep(.005)\n'+('time.sleep(30)\n' if mode=='timeout' else ''))
                peer=subprocess.Popen([sys.executable,'-c','import time;time.sleep(20)'])
                try:
                    result=subprocess.run([sys.executable,str(ROOT/'scripts/ci_stage.py'),'--timeout','0.4','--evidence',str(receipt),'--',sys.executable,str(parent)],capture_output=True,text=True,timeout=8)
                    self.assertEqual(result.returncode,1 if mode=='timeout' else 0,result.stderr)
                    proof=json.loads(receipt.read_text());self.assertTrue(proof['cleanup_confirmed']);self.assertEqual(proof['survivors'],[])
                    self.assertEqual(proof['reason'],'timeout' if mode=='timeout' else 'completed')
                    self.assertGreaterEqual(proof['owned_processes_seen'],2)
                    self.assertIsNone(peer.poll(),'Unrelated same-UID peer was killed')
                    self.assertFalse(Path('/proc',pidfile.read_text()).exists(),'Owned child was not reaped')
                    time.sleep(2.1);self.assertFalse(marker.exists(),'Detached writer survived cleanup')
                finally:peer.terminate();peer.wait(timeout=3)

    def test_termination_signals_reap_owned_children_and_preserve_peer(self):
        for requested in (signal.SIGTERM, signal.SIGINT):
            with self.subTest(signal=requested), tempfile.TemporaryDirectory() as directory:
                root=Path(directory);pidfile=root/'child';marker=root/'late';receipt=root/'receipt.json'
                child=root/'child.py'
                child.write_text('import os,signal,time\nfrom pathlib import Path\nos.setsid()\nsignal.signal(signal.SIGTERM,signal.SIG_IGN)\nPath('+repr(str(pidfile))+').write_text(str(os.getpid()))\nos.kill(os.getpid(),signal.SIGSTOP)\ntime.sleep(2)\nPath('+repr(str(marker))+').write_text("late")\n')
                parent=root/'parent.py'
                parent.write_text('import subprocess,sys,time\nsubprocess.Popen([sys.executable,'+repr(str(child))+'])\ntime.sleep(30)\n')
                peer=subprocess.Popen([sys.executable,'-c','import time;time.sleep(20)'])
                owner=subprocess.Popen([sys.executable,str(ROOT/'scripts/ci_stage.py'),'--timeout','30','--evidence',str(receipt),'--',sys.executable,str(parent)],stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
                try:
                    deadline=time.monotonic()+3
                    while not pidfile.exists() and time.monotonic()<deadline:time.sleep(.005)
                    self.assertTrue(pidfile.exists(),'Owned child did not start')
                    # Wait for actual stopped state, not merely publication of PID.
                    pid=int(pidfile.read_text())
                    while time.monotonic()<deadline:
                        state=Path('/proc',str(pid),'stat').read_text().rsplit(')',1)[1].split()[0]
                        if state=='T':break
                        time.sleep(.005)
                    self.assertEqual(state,'T')
                    started=time.monotonic();owner.send_signal(requested)
                    time.sleep(.1)
                    owner.send_signal(signal.SIGINT if requested==signal.SIGTERM else signal.SIGTERM)
                    _,errors=owner.communicate(timeout=7)
                    self.assertEqual(owner.returncode,1,errors)
                    self.assertLess(time.monotonic()-started,6)
                    proof=json.loads(receipt.read_text())
                    self.assertEqual(proof['reason'],'signal');self.assertEqual(proof['signal'],requested.name)
                    self.assertTrue(proof['cleanup_confirmed']);self.assertEqual(proof['survivors'],[])
                    self.assertFalse(Path('/proc',str(pid)).exists(),'Owned child was not reaped')
                    self.assertIsNone(peer.poll(),'Unrelated same-UID peer was signalled')
                    time.sleep(2.1);self.assertFalse(marker.exists(),'Late writer survived signal cleanup')
                finally:
                    if owner.poll() is None:owner.terminate();owner.wait(timeout=7)
                    peer.terminate();peer.wait(timeout=3)

    def test_wrapper_preserves_failure_receipt_and_does_not_accept_cleaned_failure(self):
        sys.path.insert(0,str(ROOT/'scripts'))
        try:
            import check_managed_browser_ci as wrapper
            with tempfile.TemporaryDirectory() as directory:
                output=Path(directory)
                with self.assertRaisesRegex(RuntimeError,'stage failed'):
                    wrapper.stage([sys.executable,'-c','raise SystemExit(3)'],output,'failure',2,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                proof=json.loads((output/'failure-cleanup.json').read_text())
                self.assertEqual(proof['exit_code'],3);self.assertTrue(proof['cleanup_confirmed'])
        finally:sys.path.pop(0)
