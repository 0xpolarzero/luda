"""Interactive public-MCP usability probe; synthetic fixture, no direct DOM input."""
import asyncio
import hashlib
import http.server
import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import time

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / 'artifacts/prosemirror-usability' / str(time.time_ns())
RUN.mkdir(parents=True)
PAGE = """<!doctype html><title>Synthetic paragraph editor</title>
<style>.ProseMirror {border:1px solid #555; min-height:220px; padding:16px; white-space:pre-wrap} strong{font-weight:900}</style>
<h1>Synthetic paragraph editor</h1><div id="host"></div>
<button id="save">Save synthetic document</button><script type="module" src="/app.js"></script>"""

class Fixture(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        routes = {'/app.js': ROOT / 'artifacts/prosemirror-usability/app.bundle.js',
                  '/bridge.mjs': ROOT / 'addons/editor-bridge/application/luda-prosemirror.mjs'}
        self.send_response(200)
        self.send_header('Content-Type', 'application/javascript' if self.path in routes else 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(routes[self.path].read_bytes() if self.path in routes else PAGE.encode())

    def do_POST(self):
        raw = self.rfile.read(int(self.headers['Content-Length']))
        (RUN / 'saved-model.json').write_bytes(raw)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b'saved')

async def main():
    source = subprocess.check_output(['git', '-c', f'safe.directory={ROOT}', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    # Xvfb chooses an unused display atomically; never attach the shared :1.
    rfd, wfd = os.pipe()
    xlog = (RUN / 'xvfb.log').open('w')
    xvfb = subprocess.Popen(['Xvfb', '-displayfd', str(wfd), '-screen', '0', '1280x900x24', '-nolisten', 'tcp'], pass_fds=(wfd,), stdout=xlog, stderr=xlog)
    os.close(wfd)
    display = ':' + os.read(rfd, 32).decode().strip()
    os.close(rfd)
    os.environ['DISPLAY'] = display
    os.environ['LUDA_CHROMIUM_EXECUTABLE'] = os.environ['LUDA_CHROMIUM_EXECUTABLE']
    wm_log = (RUN / 'wm.log').open('w')
    wm = subprocess.Popen(['xfwm4'], stdout=wm_log, stderr=wm_log)
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Fixture)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    metadata = {'source': source, 'display': display, 'uid': os.getuid(), 'url': f'http://127.0.0.1:{server.server_port}/', 'fixture_sha256': hashlib.sha256(PAGE.encode()).hexdigest()}
    (RUN / 'metadata.json').write_text(json.dumps(metadata, indent=2))
    print(json.dumps({'run': str(RUN), **metadata}), flush=True)
    trace = (RUN / 'trace.jsonl').open('w')
    try:
        params = StdioServerParameters(command=str(ROOT / '.venv/bin/luda'), env=dict(os.environ))
        async with stdio_client(params) as (reader, writer):
            async with ClientSession(reader, writer) as session:
                await session.initialize()
                schemas = await session.list_tools()
                (RUN / 'schemas.json').write_text(schemas.model_dump_json(indent=2))
                while True:
                    line = await asyncio.to_thread(sys.stdin.readline)
                    if not line or line.strip() == 'quit':
                        break
                    request = json.loads(line)
                    result = await session.call_tool(request['name'], request.get('arguments', {}))
                    data = result.model_dump(mode='json')
                    trace.write(json.dumps({'request': request, 'response': data}, ensure_ascii=False) + '\n')
                    trace.flush()
                    if any(c.get('type') == 'image' for c in data['content']):
                        print(json.dumps({'image_saved_in_trace': True}), flush=True)
                    else:
                        print(json.dumps(data, ensure_ascii=False), flush=True)
    finally:
        trace.close()
        server.shutdown()
        wm.terminate()
        wm.wait(timeout=10)
        xvfb.terminate()
        xvfb.wait(timeout=10)

if __name__ == '__main__':
    asyncio.run(main())
