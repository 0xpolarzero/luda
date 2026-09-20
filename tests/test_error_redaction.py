"""Unexpected exceptions must not echo application or protected input contents."""
import asyncio
from contextlib import nullcontext,redirect_stdout,redirect_stderr
import io
import json
import unittest
from unittest.mock import Mock,patch

from luda import server
from luda.common import DesktopError
from luda.desktop import Desktop

SECRET='synthetic-sensitive-value-do-not-echo'

class Backend:
    control=Mock()
    def require_supported_backend(self): pass
    def transaction(self):return nullcontext()
    def element(self,*args,**kwargs):raise RuntimeError(SECRET)
    def ready(self):return {'ready':True}

class ErrorRedaction(unittest.IsolatedAsyncioTestCase):
    async def test_public_secret_failure_response_history_and_streams_are_redacted(self):
        output=io.StringIO();errors=io.StringIO()
        with patch.object(server,'get_backend',return_value=Backend()),patch.object(server,'require_session_input'),redirect_stdout(output),redirect_stderr(errors):
            result=await server.desktop_type_secret('observed',SECRET)
            status=await server.desktop_status()
            recovered=await server.execute_async('ready')
        payload=json.loads(result.content[0].text)
        self.assertTrue(result.isError);self.assertEqual(payload['code'],'INTERNAL_ERROR');self.assertEqual(payload['effect'],'uncertain')
        self.assertRegex(payload['operation_id'],r'^[0-9a-f]{32}$')
        self.assertNotIn(SECRET,result.model_dump_json()+status.model_dump_json()+output.getvalue()+errors.getvalue())
        event=next(e for e in json.loads(status.content[0].text)['operations'] if e['operation_id']==payload['operation_id'])
        self.assertEqual(event['code'],'INTERNAL_ERROR');self.assertEqual(event['effect'],'uncertain')
        self.assertFalse(recovered.isError);self.assertFalse(server._operation_gate.locked())

    async def test_exception_stringifier_is_never_called(self):
        calls=[]
        class BadString(RuntimeError):
            def __str__(self):calls.append(True);raise AssertionError(SECRET)
        desktop=Backend();desktop.element=Mock(side_effect=BadString())
        with patch.object(server,'get_backend',return_value=desktop),patch.object(server,'require_session_input'):
            result=await server.desktop_type_secret('observed',SECRET)
        self.assertEqual(calls,[]);self.assertEqual(json.loads(result.content[0].text)['code'],'INTERNAL_ERROR')

    async def test_unexpected_secret_worker_decode_failure_is_redacted(self):
        desktop=Backend();actual=Desktop.__new__(Desktop)
        desktop.element=lambda *args,**kwargs:actual.ax({'op':'secret','text':SECRET},True)
        with patch.object(server,'get_backend',return_value=desktop),patch.object(server,'require_session_input'),patch('luda.desktop.run',return_value=b'{}'),patch('luda.desktop.json.loads',side_effect=json.JSONDecodeError(SECRET,SECRET,0)):
            result=await server.desktop_type_secret('observed',SECRET)
        self.assertNotIn(SECRET,result.model_dump_json());self.assertTrue(result.isError)

    async def test_typed_diagnostics_remain_useful(self):
        desktop=Backend();desktop.element=Mock(side_effect=DesktopError('STALE_TARGET','Inspect again: target expired.',details={'reason':'expired'}))
        with patch.object(server,'get_backend',return_value=desktop),patch.object(server,'require_session_input'):
            result=await server.execute_async('element','observed','read')
        payload=json.loads(result.content[0].text)
        self.assertEqual(payload['message'],'Inspect again: target expired.')
        self.assertEqual(payload['details'],{'reason':'expired'})

    async def test_unexpected_failure_does_not_clear_unfinished_recovery_owner(self):
        token='test-error-redaction-recovery'
        desktop=Backend()
        def fail(*args,**kwargs):server._retain_quarantine(token);raise RuntimeError(SECRET)
        desktop.element=fail
        try:
            with patch.object(server,'get_backend',return_value=desktop),patch.object(server,'require_session_input'):
                result=await server.desktop_type_secret('observed',SECRET)
                self.assertTrue(server._quarantined.is_set());self.assertIn(token,server._quarantine_owners)
                self.assertFalse(server._operation_gate.locked())
                blocked=await server.execute_async('ready')
            self.assertEqual(json.loads(blocked.content[0].text)['code'],'BUSY')
            self.assertNotIn(SECRET,result.model_dump_json())
        finally:server._release_quarantine(token)

if __name__=='__main__':unittest.main()
