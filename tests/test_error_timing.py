"""Backend failure latency stays measurable without exposing exception payloads."""
from contextlib import nullcontext
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
from luda import server
from luda.common import DesktopError

class ErrorTiming(unittest.TestCase):
    def test_typed_and_unexpected_failures_report_latency_and_keep_history(self):
        secret='synthetic-private-exception-payload'
        for failure, code, effect in [(DesktopError('STALE_TARGET','Inspect again.'),'STALE_TARGET','none'),
                                      (RuntimeError(secret),'INTERNAL_ERROR','uncertain')]:
            with self.subTest(code=code):
                backend=SimpleNamespace(transaction=lambda:nullcontext(),require_supported_backend=Mock(),control=Mock(),inspect=Mock(side_effect=failure))
                clock=SimpleNamespace(monotonic=Mock(side_effect=[100.,100.125,100.130]))
                with patch.object(server,'get_backend',return_value=backend),patch.object(server,'time',clock):
                    result=server.execute('inspect','observed-window')
                payload=json.loads(result.content[0].text)
                self.assertTrue(result.isError)
                self.assertEqual((payload['code'],payload['effect'],payload['elapsed_ms']),(code,effect,125))
                self.assertNotIn(secret,result.model_dump_json())
                self.assertEqual(server._history[-1]['operation_id'],payload['operation_id'])
                self.assertEqual(server._history[-1]['elapsed_ms'],130)
                self.assertFalse(server._operation_gate.locked())

    def test_busy_rejection_reports_time_without_backend_or_input(self):
        clock=SimpleNamespace(monotonic=Mock(side_effect=[100.,100.002,100.003]))
        with server._operation_gate,patch.object(server,'get_backend') as backend,patch.object(server,'time',clock):
            result=server.execute('inspect','observed-window')
        payload=json.loads(result.content[0].text)
        self.assertEqual((payload['code'],payload['effect'],payload['elapsed_ms']),('BUSY','none',2))
        backend.assert_not_called()

if __name__=='__main__':unittest.main()
