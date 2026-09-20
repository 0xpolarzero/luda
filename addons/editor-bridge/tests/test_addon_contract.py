"""Public separation and readiness contracts, including add-on absent from core discovery."""
import asyncio
import inspect
import json
import subprocess
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from luda.common import DesktopError
from luda.desktop import Desktop
from luda_editor_bridge.desktop import EditorDesktop
from luda_editor_bridge import server

class AddonContract(unittest.TestCase):
    def test_installed_addon_is_not_imported_or_discovered_by_core(self):
        code = """
import asyncio, json, sys
from luda import server
from luda._browser_worker import Worker
names=[x.name for x in asyncio.run(server.mcp.list_tools())]
assert names and not any(name.startswith('editor_') for name in names)
assert not any(name.startswith('luda_editor_bridge') for name in sys.modules)
assert not hasattr(Worker,'rich_type') and not hasattr(Worker,'inspect_rich')
print(json.dumps(names))
"""
        result=subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertIn('desktop_type',json.loads(result.stdout))

    def test_public_tool_names_and_edit_arguments_are_separate(self):
        from luda import server as core
        self.assertEqual(set(inspect.signature(core.desktop_type).parameters),{'element_id','text','mode'})
        tools=asyncio.run(server.mcp.list_tools())
        self.assertTrue(tools)
        self.assertTrue(all(tool.name.startswith('editor_') for tool in tools))
        typed=next(tool for tool in tools if tool.name=='editor_type')
        self.assertIn('transport',typed.inputSchema['properties'])
        self.assertIn('line_breaks',typed.inputSchema['properties'])
        self.assertNotEqual(Desktop.browser_class,EditorDesktop.browser_class)

    def test_toolbar_target_outside_owned_browser_is_refused_before_lookup(self):
        backend=EditorDesktop.__new__(EditorDesktop)
        backend.browser=SimpleNamespace(window_id='owned')
        with patch.object(Desktop,'target_window') as lookup:
            for window in ('other',None):
                with self.assertRaises(DesktopError) as caught:backend.target_window(window)
                self.assertEqual(caught.exception.code,'BROWSER_SCOPE_UNSUPPORTED')
            lookup.assert_not_called()
            backend.target_window('owned')
            lookup.assert_called_once_with('owned',True)

    def test_invalid_read_limit_is_structured_without_backend(self):
        with patch.object(server,'execute_async') as execute:
            result=asyncio.run(server.editor_read('observed',0))
            self.assertTrue(result.isError)
            self.assertEqual(json.loads(result.content[0].text)['code'],'INVALID_ARGUMENT')
            execute.assert_not_called()

    def test_editor_typing_never_routes_native_toolbar_nodes(self):
        from luda.timing import elapsed_time
        backend=EditorDesktop.__new__(EditorDesktop)
        backend.elements={'button':{'time':elapsed_time(),'provider':'native'}}
        with self.assertRaises(DesktopError) as caught:backend.type_text('button','value')
        self.assertEqual(caught.exception.code,'UNSUPPORTED_FIELD')

    def test_readiness_requires_configured_browser(self):
        from unittest.mock import AsyncMock
        from mcp.types import CallToolResult,TextContent
        for browser in (False,True):
            response=CallToolResult(content=[TextContent(type='text',text=json.dumps({'ready':True,'owned_browser':{'available':browser}}))])
            with patch.object(server,'execute_async',new=AsyncMock(return_value=response)):
                result=asyncio.run(server.editor_doctor())
            self.assertEqual(json.loads(result.content[0].text)['ready'],browser)

    def test_page_scope_refusal_is_not_misdiagnosed_as_missing_registration(self):
        backend=EditorDesktop.__new__(EditorDesktop)
        underlying={'text_fields':[],'nodes':[{'role':'push button','name':'Toolbar'}],
                    'owned_browser':{'available':False,'code':'BROWSER_SCOPE_UNSUPPORTED'}}
        with patch.object(Desktop,'inspect',return_value=underlying):
            result=backend.inspect('owned')
        self.assertEqual(result['editor_bridge']['status'],'unsupported_page_scope')
        self.assertEqual(result['owned_browser']['code'],'BROWSER_SCOPE_UNSUPPORTED')
        self.assertEqual(result['nodes'],underlying['nodes'])
        self.assertNotIn('register',result['editor_bridge']['next_step'])

    def test_connected_unsupported_document_is_distinct_from_no_matching_editor(self):
        backend=EditorDesktop.__new__(EditorDesktop)
        for fields,status in (([],'no_matching_editor'),([{'supported':False,'unsupported_reason':'TEXT_REPRESENTATION_UNSUPPORTED'}],'connected')):
            with patch.object(Desktop,'inspect',return_value={'text_fields':fields,'nodes':[]}):
                result=backend.inspect('owned')
            self.assertEqual(result['editor_bridge']['status'],status)
            self.assertEqual(result['editor_bridge']['supported_editors'],0)
