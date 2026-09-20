"""Malformed MCP input must never become a coerced GUI mutation."""
import json
import unittest
from unittest.mock import AsyncMock, patch
from luda.server import mcp


class ProtocolValidation(unittest.IsolatedAsyncioTestCase):
    async def test_bad_values_and_unknown_fields_never_dispatch(self):
        cases=[
            ('desktop_click',dict(window_id='w',snapshot_id='s',x=True,y=2)),
            ('desktop_click',dict(window_id='w',snapshot_id='s',x='1',y=2)),
            ('desktop_click',dict(window_id='w',snapshot_id='s',x=1,y=2,count=True)),
            ('desktop_set_checked',dict(element_id='e',checked='false')),
            ('desktop_set_checked',dict(element_id='e',checked=1)),
            ('desktop_select',dict(element_id='e',start_offset=True,end_offset=2)),
            ('desktop_window',dict(window_id='w',action='move',x=1.5,y=2)),
            ('desktop_type',dict(element_id='e',text='SYNTHETIC_SECRET',mdoe='replace')),
            ('desktop_type_secret',dict(text='SYNTHETIC_SECRET')),
            ('desktop_inspect',dict(window_id='w',states='["enabled"]')),
        ]
        with patch('luda.server.execute_async',new_callable=AsyncMock) as dispatch:
            for name,args in cases:
                with self.subTest(name=name,args=args):
                    result=await mcp.call_tool(name,args)
                    self.assertTrue(result.isError)
                    value=json.loads(result.content[0].text)
                    self.assertEqual(value['code'],'INVALID_ARGUMENT');self.assertEqual(value['effect'],'none')
                    self.assertNotIn('SYNTHETIC_SECRET',result.content[0].text)
            dispatch.assert_not_called()

    async def test_repair_hints_contain_schema_names_but_no_submitted_values(self):
        result=await mcp.call_tool('desktop_click',dict(window_id='w',snapshot_id='s',x='secret-value',y=2))
        text=result.content[0].text;issue=json.loads(text)['issues'][0]
        self.assertEqual(issue,{'rule':'type','parameter':'x','expected':'number'})
        self.assertNotIn('secret-value',text)
        result=await mcp.call_tool('desktop_type_secret',dict(text='secret-value',secret_field='private'))
        text=result.content[0].text
        self.assertNotIn('secret-value',text);self.assertNotIn('secret_field',text);self.assertNotIn('private',text)
        self.assertIn('element_id',text)

    async def test_protocol_advertises_product_version_not_sdk_version(self):
        from importlib.metadata import version
        options=mcp._mcp_server.create_initialization_options()
        self.assertEqual(options.server_name,'luda')
        self.assertEqual(options.server_version,version('luda'))

    async def test_schemas_refuse_unknown_properties(self):
        for tool in await mcp.list_tools():
            self.assertIs(tool.inputSchema.get('additionalProperties'),False,tool.name)

    async def test_native_json_numbers_and_boolean_dispatch(self):
        from mcp.types import CallToolResult,TextContent
        with patch('luda.server.execute_async',new_callable=AsyncMock,return_value=CallToolResult(content=[TextContent(type='text',text='{}')])) as dispatch:
            await mcp.call_tool('desktop_click',dict(window_id='w',snapshot_id='s',x=1,y=2.5,count=2))
            self.assertEqual(dispatch.call_args.args,('pointer','w','s',1.0,2.5))
            await mcp.call_tool('desktop_set_checked',dict(element_id='e',checked=False))
            self.assertIs(dispatch.call_args.kwargs['checked'],False)
