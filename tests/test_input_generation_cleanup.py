"""Final disposable-Xvfb teardown must reap or fail, without retrying input."""
import subprocess
import os
import time
import unittest
from unittest.mock import Mock
from live_input_generation import stop_owned_server, read_proof


class OwnedServerCleanupTests(unittest.TestCase):
    def test_already_exited_is_not_signalled(self):
        process = Mock(returncode=0)
        process.poll.return_value = 0
        self.assertEqual(stop_owned_server(process), {'term_to_kill_escalated': False, 'returncode': 0})
        process.terminate.assert_not_called()
        process.kill.assert_not_called()
        process.wait.assert_not_called()

    def test_ordinary_term_is_bounded(self):
        process = Mock(returncode=-15)
        process.poll.return_value = None
        result = stop_owned_server(process, timeout=.1)
        self.assertFalse(result['term_to_kill_escalated'])
        process.terminate.assert_called_once_with()
        process.wait.assert_called_once_with(timeout=.1)
        process.kill.assert_not_called()

    def test_stalled_term_escalates_once_and_reaps(self):
        process = Mock(returncode=-9)
        process.poll.return_value = None
        process.wait.side_effect = [subprocess.TimeoutExpired('owned Xvfb', .1), -9]
        result = stop_owned_server(process, timeout=.1)
        self.assertEqual(result, {'term_to_kill_escalated': True, 'returncode': -9})
        process.terminate.assert_called_once_with()
        process.kill.assert_called_once_with()
        self.assertEqual(process.wait.call_count, 2)
        self.assertTrue(all(call.kwargs == {'timeout': .1} for call in process.wait.call_args_list))

    def test_unreaped_child_still_fails(self):
        process = Mock()
        process.poll.return_value = None
        process.wait.side_effect = subprocess.TimeoutExpired('owned Xvfb', .1)
        with self.assertRaises(subprocess.TimeoutExpired):
            stop_owned_server(process, timeout=.1)
        process.kill.assert_called_once_with()
        self.assertEqual(process.wait.call_count, 2)

    def test_signal_failure_is_not_hidden(self):
        process = Mock()
        process.poll.return_value = None
        process.terminate.side_effect = PermissionError('not signallable')
        with self.assertRaises(PermissionError):
            stop_owned_server(process)
        process.kill.assert_not_called()


class GuardianProofTests(unittest.TestCase):
    def pipe(self):
        reader, writer=os.pipe()
        self.addCleanup(os.close, reader);self.addCleanup(os.close, writer)
        return reader,writer
    def test_complete_receipt(self):
        reader,writer=self.pipe();os.write(writer,b'{"held":true}\n')
        with os.fdopen(os.dup(reader),'rb',buffering=0) as stream:
            self.assertEqual(read_proof(stream),{'held':True})
    def test_partial_receipt_has_bounded_deadline(self):
        reader,writer=self.pipe();os.write(writer,b'{"held":')
        began=time.monotonic()
        with os.fdopen(os.dup(reader),'rb',buffering=0) as stream, self.assertRaises(TimeoutError):
            read_proof(stream,timeout=.02)
        self.assertLess(time.monotonic()-began,.5)
    def test_eof_is_not_a_receipt(self):
        reader,writer=os.pipe();os.close(writer)
        with os.fdopen(reader,'rb',buffering=0) as stream, self.assertRaises(AssertionError):
            read_proof(stream)
