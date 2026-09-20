"""Report projection cannot turn provider contents or arbitrary history into logs."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import AsyncMock, patch
from luda import reporting as r
from luda import server
from mcp.types import CallToolResult, TextContent


class ReportPrivacy(unittest.TestCase):
    def test_health_strict_boolean_whitelist_and_nested_injected_content(self):
        marker='SYNTHETIC-PRIVATE-CONTENT'
        health={'ready':True,'display_available':marker,'title':marker,'display':'/secret/path',
                'dependencies':{'scrot':True,'xclip':marker,'unknown':marker},
                'control':{'available':True,'paused':False,'reason':marker},
                'keyboard':{'available':1,'message':marker},'session_state':{'input_ready':None,'detail':marker}}
        result=r.project_health(health)
        self.assertNotIn(marker,json.dumps(result));self.assertNotIn('/secret',json.dumps(result))
        self.assertTrue(result['ready']);self.assertIsNone(result['display_available'])
        self.assertIsNone(result['keyboard']['available']);self.assertIsNone(result['dependencies']['xclip'])

    def test_history_bounds_ids_enums_numbers_no_arbitrary_details(self):
        history=[{'operation_id':'a'*32,'method':'element','effect':'verified','ok':True,'elapsed_ms':42,
                  'action':'SENSITIVE','text':'SENSITIVE','message':'SENSITIVE','details':{'path':'SENSITIVE'}}]*40
        rows=r.project_history(history)
        self.assertEqual(len(rows),32);self.assertNotIn('SENSITIVE',json.dumps(rows))
        for bad in ('SENSITIVE',[],{},True,None):
            row=r.project_history([dict(operation_id=bad,method=bad,effect=bad,elapsed_ms=bad)])
            self.assertNotIn('SENSITIVE',json.dumps(row))
        self.assertEqual(r.project_history([{'elapsed_ms':float('inf')},{'elapsed_ms':-1}]),[])

    def test_environment_projection_fixed_packages_and_malformed_versions(self):
        with patch.object(r.platform,'freedesktop_os_release',return_value={'ID':'SENSITIVE','VERSION_ID':'/secret','PRETTY_NAME':'SENSITIVE'}),patch.object(r.platform,'machine',return_value='SENSITIVE'),patch.object(r.platform,'python_version',return_value='3.12.3'),patch.object(r,'version',return_value='SENSITIVE'),patch.object(r,'run',return_value=b'scrot\t1.10\nunknown\tSENSITIVE\nxclip\tSENSITIVE\n') as run:
            value=r.environment_summary()
        self.assertNotIn('SENSITIVE',json.dumps(value));self.assertNotIn('/secret',json.dumps(value))
        self.assertEqual(value['packages']['scrot'],'1.10');self.assertIsNone(value['packages']['xclip'])
        self.assertEqual(run.call_args.kwargs['max_output_bytes'],16384)
        self.assertEqual(run.call_args.kwargs['timeout'],2)

    def test_doctor_error_content_never_reaches_report(self):
        error=CallToolResult(isError=True,content=[TextContent(type='text',text=json.dumps({'message':'SENSITIVE','details':{'path':'SENSITIVE'}}))])
        with patch.object(server,'execute_async',new=AsyncMock(return_value=error)),patch.object(r,'environment_summary',return_value={}):
            result=asyncio.run(server.desktop_report())
        value=json.loads(result.content[0].text)
        self.assertNotIn('SENSITIVE',json.dumps(value));self.assertIsNone(value['health']['ready'])
        self.assertEqual(value['effect'],'none');self.assertFalse(result.isError)

    def test_unexpected_environment_and_doctor_exceptions_are_content_free(self):
        with patch.object(server, 'execute_async', new=AsyncMock(side_effect=RuntimeError('SENSITIVE-DOCTOR'))), patch.object(r, 'version', side_effect=RuntimeError('SENSITIVE-PACKAGE')):
            value = json.loads(asyncio.run(server.desktop_report()).content[0].text)
        self.assertNotIn('SENSITIVE', json.dumps(value))
        self.assertEqual(value['environment'], r.empty_environment())
        self.assertIsNone(value['health']['ready'])

    def test_malformed_doctor_payload_cannot_escape_projection(self):
        for payload in ('not JSON SENSITIVE', '["SENSITIVE"]', '{"ready":"SENSITIVE","details":{"text":"SENSITIVE"}}'):
            result = CallToolResult(content=[TextContent(type='text', text=payload)])
            with patch.object(server, 'execute_async', new=AsyncMock(return_value=result)), patch.object(r, 'environment_summary', return_value={}):
                report = asyncio.run(server.desktop_report())
            self.assertNotIn('SENSITIVE', report.content[0].text)

    def test_mcp_uses_snapshot_of_prior_metadata_not_doctor_payload(self):
        from collections import deque
        history = deque([{'operation_id': 'a'*32, 'method': 'drag_between', 'effect': 'verified', 'ok': True, 'elapsed_ms': 3, 'details': 'SENSITIVE'}], maxlen=32)
        async def doctor(*args):
            history.append({'method': 'doctor', 'ok': True})
            return CallToolResult(content=[TextContent(type='text', text='{"ready":true,"operations":["SENSITIVE"]}')])
        with patch.object(server, '_history', history), patch.object(server, 'execute_async', side_effect=doctor), patch.object(r, 'environment_summary', return_value={}):
            value = json.loads(asyncio.run(server.desktop_report()).content[0].text)
        self.assertEqual(value['history_scope'], 'current_mcp_process')
        self.assertEqual(len(value['operations']), 1)
        self.assertEqual(value['operations'][0]['method'], 'drag_between')
        self.assertNotIn('SENSITIVE', json.dumps(value))

    def test_codes_and_semantic_verbs_use_fixed_vocabulary(self):
        rows = r.project_history([
            {'method': 'element', 'action': 'invoke', 'code': 'STALE_TARGET'},
            {'method': 'element', 'action': 'SENSITIVE', 'code': 'SENSITIVE'},
            {'method': 'paste', 'action': 'secret', 'code': ['INTERNAL_ERROR']}])
        self.assertEqual(rows[0], {'method': 'element', 'action': 'invoke', 'code': 'STALE_TARGET'})
        self.assertEqual(rows[1], {'method': 'element'})
        self.assertEqual(rows[2], {'method': 'paste'})
        for code in ('ACCESSIBILITY_ERROR', 'ACCESSIBILITY_UNAVAILABLE', 'AMBIGUOUS_ACCESSIBILITY_WINDOW', 'INVALID_SELECTION', 'LAUNCH_FAILED', 'NOT_PROTECTED_FIELD', 'SELECTION_TOO_LARGE', 'SELECTION_UNVERIFIABLE', 'TARGET_IDENTITY_UNAVAILABLE', 'UNSUPPORTED_OPERATION'):
            with self.subTest(code=code):
                self.assertEqual(r.project_history([{'code': code, 'message': 'SENSITIVE'}]), [{'code': code}])
        self.assertEqual(r.project_history([{'code': 'PRIVATE_CUSTOM_PROVIDER_ERROR'}]), [])


    def test_execute_records_only_fixed_semantic_verb_not_invoke_name(self):
        from collections import deque
        from luda.common import DesktopError
        history = deque(maxlen=32)
        with patch.object(server, '_history', history), patch.object(server, 'get_backend', side_effect=DesktopError('STALE_TARGET', 'SENSITIVE')):
            server.execute('element', 'SENSITIVE-ELEMENT', 'invoke', action='SENSITIVE-NATIVE-ACTION')
            server.execute('element', 'SENSITIVE-ELEMENT', 'SENSITIVE-VERB')
        self.assertEqual(history[0]['action'], 'invoke')
        self.assertEqual(history[0]['code'], 'STALE_TARGET')
        self.assertNotIn('action', history[1])
        self.assertNotIn('SENSITIVE', json.dumps(history.copy(), default=list))
        rows = r.project_history(history)
        self.assertEqual(rows[0]['action'], 'invoke')
        self.assertEqual(rows[0]['code'], 'STALE_TARGET')

    def test_identity_projection_reuses_doctor_without_arbitrary_fields(self):
        health = {'versions': {'driver_version': '0.1.0', 'tool_schema': {'sha256': 'a'*64, 'scope': 'SENSITIVE'}, 'bundled_skill': {'sha256': 'SENSITIVE', 'status': 'SENSITIVE', 'reason': 'SENSITIVE'}}}
        response = CallToolResult(content=[TextContent(type='text', text=json.dumps(health))])
        with patch.object(server, 'desktop_doctor', new=AsyncMock(return_value=response)) as doctor, patch.object(r, 'environment_summary', return_value={}):
            value = json.loads(asyncio.run(server.desktop_report()).content[0].text)
        doctor.assert_awaited_once()
        self.assertEqual(value['versions']['tool_schema']['sha256'], 'a'*64)
        self.assertIsNone(value['versions']['bundled_skill']['sha256'])
        self.assertIsNone(value['versions']['bundled_skill']['status'])
        self.assertNotIn('SENSITIVE', json.dumps(value))

    def test_schema_readonly_no_free_text_parameters(self):
        tool=next(t for t in asyncio.run(server.mcp.list_tools()) if t.name=='desktop_report')
        self.assertTrue(tool.annotations.readOnlyHint)
        self.assertEqual(tool.inputSchema['properties'],{})
        self.assertFalse(tool.inputSchema['additionalProperties'])

    def test_cli_fresh_history_and_stdout_json_without_desktop_environment(self):
        env=dict(os.environ)
        for key in ('DISPLAY','DBUS_SESSION_BUS_ADDRESS','XAUTHORITY'):
            env.pop(key,None)
        with __import__('tempfile').TemporaryDirectory() as directory:
            value=subprocess.run([sys.executable,'-m','luda.server','report'],env=env,cwd=directory,capture_output=True,text=True,timeout=20)
            self.assertEqual(list(Path(directory).iterdir()),[])
        self.assertEqual(value.returncode,0,value.stderr)
        report=json.loads(value.stdout)
        self.assertEqual(report['history_scope'],'fresh_cli_process');self.assertEqual(report['operations'],[])
        self.assertIs(report['health']['display_available'],False)
        self.assertNotIn('display',report['health']);self.assertEqual(report['history_limit'],32)

if __name__=='__main__':unittest.main()
