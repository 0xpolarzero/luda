"""Persistent actual stdio MCP client controlled through numbered JSON requests."""
import asyncio
import base64
import json
import os
from pathlib import Path
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(os.environ['LUDA_PROBE_DIR'])

async def main():
    async with stdio_client(StdioServerParameters(command=os.environ['LUDA_PROBE_BINARY'], env=dict(os.environ))) as (reader, writer):
        async with ClientSession(reader, writer) as session:
            await session.initialize()
            catalog = await session.list_tools()
            (ROOT / 'schemas.json').write_text(catalog.model_dump_json(indent=2))
            for index in range(1, 100):
                request = ROOT / f'request-{index}.json'
                while not request.exists():
                    await asyncio.sleep(0.1)
                args = json.loads(request.read_text())
                if args.get('close'):
                    break
                result = await session.call_tool(args['name'], args.get('arguments', {}))
                serialized = result.model_dump(mode='json')
                for item_index, item in enumerate(serialized['content']):
                    if item['type'] == 'image':
                        path = ROOT / f'image-{index}-{item_index}.png'
                        path.write_bytes(base64.b64decode(item.pop('data')))
                        item['saved_image'] = str(path)
                (ROOT / f'response-{index}.json').write_text(json.dumps(serialized, indent=2))

asyncio.run(main())
