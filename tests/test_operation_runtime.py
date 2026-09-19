import os
import subprocess
import sys
import threading
import time
import unittest
from unittest.mock import Mock, patch

from luda.common import DesktopError, operation_scope, run
from luda.desktop import Desktop


class OperationRuntime(unittest.TestCase):
    def test_overall_deadline_bounds_multiple_commands(self):
        began = time.monotonic()
        with self.assertRaises(DesktopError) as error:
            with operation_scope(timeout=.12):
                run([sys.executable, '-c', 'import time; time.sleep(.07)'])
                run([sys.executable, '-c', 'import time; time.sleep(.07)'])
        self.assertEqual(error.exception.code, 'TIMEOUT')
        self.assertLess(time.monotonic()-began, 1)

    def test_cancellation_interrupts_running_child(self):
        cancelled = threading.Event()
        timer = threading.Timer(.12, cancelled.set)
        timer.start()
        try:
            with self.assertRaises(DesktopError) as error:
                with operation_scope(cancelled=cancelled):
                    run([sys.executable, '-c', 'import time; time.sleep(10)'], effect='uncertain')
            self.assertEqual(error.exception.code, 'CANCELLED')
            self.assertEqual(error.exception.effect, 'uncertain')
        finally:
            timer.cancel()

    def test_cancelled_before_input_and_cleanup_allowed(self):
        cancelled = threading.Event(); cancelled.set()
        with operation_scope(cancelled=cancelled):
            with self.assertRaises(DesktopError) as error:
                run([sys.executable, '-c', 'raise Exception("must not run")'])
            self.assertEqual(error.exception.effect, 'none')
            self.assertEqual(run([sys.executable, '-c', 'print("released")'], cleanup=True), b'released\n')

    def test_large_stdin_survives_polling(self):
        data = ('日本語\n'*40_000).encode()
        with operation_scope():
            result = run([sys.executable, '-c', 'import sys,time; time.sleep(.1); sys.stdout.buffer.write(sys.stdin.buffer.read())'], data=data)
        self.assertEqual(result, data)

    def test_invalid_pointer_request_has_no_input(self):
        desktop = object.__new__(Desktop)
        desktop.point = Mock(return_value=(10, 10))
        bad = [dict(kind='bogus'), dict(direction='bogus'), dict(count=True), dict(count=1.5), dict(x=float('nan')), dict(x=float('inf'))]
        for arguments in bad:
            with self.subTest(arguments=arguments), patch('luda.desktop.run') as command:
                kwargs = dict(window_id='w', snapshot_id='s', x=1, y=2)
                kwargs.update(arguments)
                with self.assertRaises(DesktopError): desktop.pointer(**kwargs)
                command.assert_not_called()

    def test_close_is_idempotent_and_independent(self):
        desktop = object.__new__(Desktop)
        desktop.closed = False
        desktop.clipboard_owner = Mock()
        desktop.clipboard_owner.poll.return_value = None
        desktop.clipboard_owner.terminate.side_effect = OSError('failed signal')
        desktop.x = Mock(); desktop.lockfd = 99
        with patch('luda.desktop.os.close') as close:
            desktop.close(); desktop.close()
        desktop.x.close.assert_called_once()
        close.assert_called_once_with(99)
        self.assertEqual(len(desktop.cleanup_errors), 1)
