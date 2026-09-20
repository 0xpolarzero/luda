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
from urllib.parse import parse_qs

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[2]
RUN = ROOT / 'artifacts/browser-usability' / str(time.time_ns())
RUN.mkdir(parents=True)
PAGE = '''<!doctype html><title>Synthetic Browser Usability Form</title>
<h1>Synthetic Browser Usability Form</h1>
<form method="post" action="/submit">
<p><label>Reference <input name="reference" aria-label="Reference"></label></p>
<p><label>Message <textarea name="message" aria-label="Message" rows="8" cols="60"></textarea></label></p>
<button type="submit">Submit synthetic record</button></form>'''

class Fixture(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(PAGE.encode())

    def do_POST(self):
        raw = self.rfile.read(int(self.headers['Content-Length']))
        record = {'raw_utf8': raw.decode(), 'form': parse_qs(raw.decode(), keep_blank_values=True)}
        (RUN / 'submission.json').write_text(json.dumps(record, ensure_ascii=False, indent=2))
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(b'<!doctype html><title>Submitted</title><h1>Synthetic record submitted</h1>')

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
    os.environ['LUDA_CHROMIUM_EXECUTABLE'] = '/workspace/silo-desktop-research/browsers/chromium-1243/chrome-linux-arm64/chrome'
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
                async def call(tool_name, **arguments):
                    request = {'name': tool_name, 'arguments': arguments}
                    result = await session.call_tool(tool_name, arguments)
                    data = result.model_dump(mode='json')
                    trace.write(json.dumps({'request': request, 'response': data}, ensure_ascii=False) + '\n')
                    trace.flush()
                    print(json.dumps(data, ensure_ascii=False), flush=True)
                    return json.loads(data['content'][0]['text'])

                if '--scripted' in sys.argv:
                    doctor = await call('desktop_doctor')
                    assert doctor['owned_browser']['available']
                    opened = await call('desktop_open_browser', url=metadata['url'], lifetime='temporary_session')
                    assert opened['ok'], opened
                    wid = opened['window_id']
                    assert (await call('desktop_activate', window_id=wid))['ok']
                    fields = (await call('desktop_inspect', window_id=wid, role='entry'))['text_fields']
                    ids = {field['name']: field['element_id'] for field in fields}
                    initial = 'A😀B café é\t東京\nsecond line\n\n'
                    expected = 'A🧪ΩB café é\t東京\nsecond line\n\n'
                    for name, value in [('Reference', 'R-東京-😀'), ('Message', initial)]:
                        assert (await call('desktop_type', element_id=ids[name], text=value, mode='replace'))['ok']
                    assert (await call('desktop_select', element_id=ids['Message'], start_offset=1, end_offset=2))['ok']
                    assert (await call('desktop_type', element_id=ids['Message'], text='🧪Ω', mode='insert'))['ok']
                    assert (await call('desktop_read_text', element_id=ids['Message']))['text'] == expected
                    inspected = await call('desktop_inspect', window_id=wid, name='Submit synthetic record')
                    button = next(node for node in inspected['nodes'] if node['name'] == 'Submit synthetic record' and node['role'] == 'push button')
                    assert 'press' in button['actions']
                    assert (await call('desktop_invoke', element_id=button['element_id'], action='press'))['ok']
                    assert (await call('desktop_windows', query='Submitted'))['total_matches'] == 1
                    stale = await call('desktop_type', element_id=ids['Message'], text='SHOULD NOT ARRIVE')
                    assert stale['code'] == 'STALE_TARGET' and stale['effect'] == 'none', stale
                    # Only now read the independently recorded HTTP oracle. Form serialization
                    # converts LF to CRLF; preserve raw bytes rather than hiding that conversion.
                    oracle = json.loads((RUN / 'submission.json').read_text())
                    assert oracle['form'] == {'reference': ['R-東京-😀'], 'message': [expected.replace('\n', '\r\n')]}
                    (RUN / 'verification.json').write_text(json.dumps({'exact_readback': True, 'http_form_exact_with_html_crlf_serialization': True, 'stale_refused': True}, indent=2))
                while '--scripted' not in sys.argv:
                    line = await asyncio.to_thread(sys.stdin.readline)
                    if not line or line.strip() == 'quit':
                        break
                    request = json.loads(line)
                    result = await session.call_tool(request['name'], request.get('arguments', {}))
                    data = result.model_dump(mode='json')
                    trace.write(json.dumps({'request': request, 'response': data}, ensure_ascii=False) + '\n')
                    trace.flush()
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
