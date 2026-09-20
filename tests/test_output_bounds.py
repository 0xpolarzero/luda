"""Memory/output bounds using real child processes and independent late-effect oracles."""
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from luda.common import DesktopError, operation_scope, run


class OutputBounds(unittest.TestCase):
    def test_exact_combined_limit_succeeds(self):
        actual = run([sys.executable,'-c','import os;os.write(1,b"o"*2048);os.write(2,b"e"*2048)'],max_output_bytes=4096)
        self.assertEqual(actual,b'o'*2048)

    def test_stdout_overflow_has_no_payload_in_error(self):
        marker='private-fixture-marker'
        with self.assertRaises(DesktopError) as raised:
            run([sys.executable,'-c','import os,sys;os.write(1,sys.argv[1].encode()*1000)',marker],max_output_bytes=128,effect='uncertain')
        self.assertEqual(raised.exception.code,'OUTPUT_LIMIT')
        self.assertEqual(raised.exception.effect,'uncertain')
        self.assertNotIn(marker,str(raised.exception))
        self.assertEqual(raised.exception.details,{'limit_bytes':128})

    def test_stderr_counts_toward_limit_without_echoing_it(self):
        with self.assertRaises(DesktopError) as raised:
            run([sys.executable,'-c','import os;os.write(2,b"do-not-echo"*1000)'],max_output_bytes=100)
        self.assertEqual(raised.exception.code,'OUTPUT_LIMIT')
        self.assertNotIn('do-not-echo',str(raised.exception))

    def test_combined_streams_cannot_each_consume_entire_allowance(self):
        with self.assertRaises(DesktopError) as raised:
            run([sys.executable,'-c','import os;os.write(1,b"a"*600);os.write(2,b"b"*600)'],max_output_bytes=1000)
        self.assertEqual(raised.exception.code,'OUTPUT_LIMIT')

    def test_zero_limit_allows_only_empty_output(self):
        self.assertEqual(run([sys.executable,'-c','pass'],max_output_bytes=0),b'')
        with self.assertRaises(DesktopError) as raised:
            run([sys.executable,'-c','print("x")'],max_output_bytes=0)
        self.assertEqual(raised.exception.code,'OUTPUT_LIMIT')

    def test_invalid_limits_rejected_before_process_launch(self):
        with patch('luda.common.subprocess.Popen') as popen:
            for limit in (-1,True,1.5,float('inf'),None):
                with self.subTest(limit=limit),self.assertRaises(DesktopError):
                    run(['must-not-launch'],max_output_bytes=limit)
            popen.assert_not_called()

    def test_interleaved_large_output_does_not_deadlock(self):
        value=run([sys.executable,'-c','import os\nfor i in range(128):\n os.write(1,b"o"*8192)\n os.write(2,b"e"*8192)'],max_output_bytes=2*1024*1024)
        self.assertEqual(value,b'o'*(1024*1024))

    def test_output_limit_kills_descendant_before_late_write(self):
        with tempfile.TemporaryDirectory() as directory:
            sentinel=Path(directory)/'late'
            child='import pathlib,sys,time;time.sleep(.3);pathlib.Path(sys.argv[1]).write_text("late")'
            parent='import subprocess,sys,os,time;subprocess.Popen([sys.executable,"-c",sys.argv[1],sys.argv[2]]);os.write(1,b"x"*4096);time.sleep(30)'
            with self.assertRaises(DesktopError) as raised:
                run([sys.executable,'-c',parent,child,str(sentinel)],max_output_bytes=100)
            self.assertEqual(raised.exception.code,'OUTPUT_LIMIT')
            time.sleep(.35)
            self.assertFalse(sentinel.exists())

    def test_overflow_repetition_does_not_leak_pipe_or_selector_descriptors(self):
        before=len(os.listdir('/proc/self/fd'))
        for _ in range(10):
            with self.assertRaises(DesktopError):
                run([sys.executable,'-c','print("x"*4096)'],max_output_bytes=10)
        self.assertLessEqual(len(os.listdir('/proc/self/fd')),before+1)

    def test_cancellation_while_draining_output_remains_bounded(self):
        cancelled=threading.Event()
        timer=threading.Timer(.08,cancelled.set)
        timer.start()
        try:
            began=time.monotonic()
            with operation_scope(cancelled=cancelled),self.assertRaises(DesktopError) as raised:
                run([sys.executable,'-c','import os,time\nwhile True:\n os.write(1,b"x"*1024)\n time.sleep(.005)'],effect='uncertain')
            self.assertEqual(raised.exception.code,'CANCELLED')
            self.assertEqual(raised.exception.effect,'uncertain')
            self.assertLess(time.monotonic()-began,1)
        finally:
            timer.cancel()


if __name__=='__main__':
    unittest.main()
