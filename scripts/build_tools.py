#!/usr/bin/env python3
"""Generate the public tool reference from actual MCP declarations, without importing the server."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def render():
    module = ast.parse((ROOT / 'src/luda/server.py').read_text())
    lines = ['# Tool reference', '', 'Generated from the registered MCP tools by `python scripts/build_tools.py`.', '',
             'Window and element IDs come from observations. Coordinates use returned screenshot pixels. '
             'Read `effect` and the named verification before deciding whether to repeat an action.', '']
    for node in module.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) or not any(
            isinstance(d, ast.Call) and ast.unparse(d.func) == 'mcp.tool' for d in node.decorator_list):
            continue
        lines += [f'## `{node.name}`', '', '```python', f'{node.name}({ast.unparse(node.args)})', '```', '',
                  ast.get_docstring(node) or '', '']
    return '\n'.join(lines)

if __name__ == '__main__':
    (ROOT / 'docs/TOOLS.md').write_text(render())
