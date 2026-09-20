"""Validate the advertised JSON contract before FastMCP's permissive coercion."""
import json
from jsonschema import Draft202012Validator
from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent


class DesktopMCP(FastMCP):
    async def list_tools(self):
        tools = await super().list_tools()
        for tool in tools:
            # A misspelled parameter must not silently choose a mutation default.
            tool.inputSchema['additionalProperties'] = False
        return tools

    async def call_tool(self, name, arguments):
        tool = next((tool for tool in await self.list_tools() if tool.name == name), None)
        if tool is not None and not Draft202012Validator(tool.inputSchema).is_valid(arguments):
            # Validation errors can contain submitted secrets. Return no values,
            # invalid property names or repr of the request in diagnostics.
            return CallToolResult(isError=True, content=[TextContent(type='text', text=json.dumps({
                'ok': False, 'code': 'INVALID_ARGUMENT', 'effect': 'none',
                'message': 'Arguments do not match the tool schema. No desktop operation started.'}))])
        return await super().call_tool(name, arguments)
