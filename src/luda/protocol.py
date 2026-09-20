"""Validate the advertised JSON contract before FastMCP's permissive coercion."""
import json
from itertools import islice
from jsonschema import Draft202012Validator
from mcp.server.fastmcp import FastMCP
from mcp.types import CallToolResult, TextContent


class DesktopMCP(FastMCP):
    def __init__(self, *args, product_version, **kwargs):
        super().__init__(*args, **kwargs)
        # FastMCP 1.30 has no public version argument and otherwise advertises
        # the MCP SDK package version as this application's server version.
        self._mcp_server.version = product_version

    async def list_tools(self):
        tools = await super().list_tools()
        for tool in tools:
            # A misspelled parameter must not silently choose a mutation default.
            tool.inputSchema['additionalProperties'] = False
        return tools

    async def call_tool(self, name, arguments):
        tool = next((tool for tool in await self.list_tools() if tool.name == name), None)
        errors = list(islice(Draft202012Validator(tool.inputSchema).iter_errors(arguments), 5)) if tool is not None else []
        if errors:
            known = tool.inputSchema.get('properties', {})
            issues = []
            for error in errors:
                path = list(error.path)
                issue = {'rule': error.validator}
                if path and path[0] in known:
                    issue['parameter'] = path[0]
                if error.validator == 'required' and isinstance(arguments, dict):
                    issue['missing_parameters'] = [name for name in tool.inputSchema.get('required', []) if name not in arguments]
                if error.validator == 'additionalProperties':
                    issue['accepted_parameters'] = list(known)
                if error.validator in ('type', 'enum', 'minimum', 'maximum', 'minLength', 'maxLength'):
                    issue['expected'] = error.validator_value
                issues.append(issue)
            # Validation errors can contain submitted secrets. Return no values,
            # invalid property names or repr of the request in diagnostics.
            return CallToolResult(isError=True, content=[TextContent(type='text', text=json.dumps({
                'ok': False, 'code': 'INVALID_ARGUMENT', 'effect': 'none',
                'message': 'Arguments do not match the tool schema. No desktop operation started.',
                'issues': issues}))])
        return await super().call_tool(name, arguments)
