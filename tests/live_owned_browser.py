"""Actual MCP owned-browser fields, native input oracle and temporary cleanup."""
import argparse
import base64
import asyncio
import http.server
import json
import os
import signal
from unittest.mock import patch
from pathlib import Path
import sys
import threading
import time
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/owned-browser'
HTML='''<!doctype html><meta charset="utf-8"><title>Luda owned browser contract</title>
<label>Exact field<textarea id="text" aria-label="Exact field" style="width:650px;height:220px"></textarea></label>
<label>Single field<input id="single" aria-label="Single field"></label>
<input type="password" id="protected" aria-label="Protected field" value="synthetic-protected">
<a href="/download" download>Download fixture</a>
<button id="replace" onclick="let n=document.querySelector('#text');n.replaceWith(n.cloneNode(true));wire();save()">Replace field</button>
<button onclick="location.reload()">Reload document</button>
<button onclick="let f=document.createElement('iframe');f.srcdoc='frame fixture';document.body.append(f);save()">Add frame</button>
<script>
const events=[];function save(){fetch('/oracle',{method:'POST',body:JSON.stringify({frames:document.querySelectorAll('iframe').length,text:document.querySelector('#text').value,single:document.querySelector('#single').value,selection:[document.querySelector('#text').selectionStart,document.querySelector('#text').selectionEnd],events:events.slice(-30)})})}
function wire(){for(const n of document.querySelectorAll('textarea,input:not([type=password])'))for(const type of ['input','beforeinput','select','compositionstart','compositionupdate','compositionend','keydown','keyup'])n.addEventListener(type,e=>{events.push({type:e.type,inputType:e.inputType??null,trusted:e.isTrusted,isComposing:e.isComposing??null,key:e.key??null,code:e.code??null,data:e.data??null});queueMicrotask(save)})}wire();save();
</script>'''


async def main(executable):
    if os.getuid()==0 or os.environ.get('LUDA_ISOLATED_TEST_DISPLAY')!='1':raise RuntimeError('Private ordinary-UID display required')
    OUT.mkdir(parents=True,exist_ok=True);cases=[];state={};lock=threading.Lock()
    def record(name,ok,details=None):
        cases.append({'case':name,'passed':bool(ok),'details':details})
        (OUT/'results.json').write_text(json.dumps(cases,ensure_ascii=False,indent=2))
        if not ok:raise AssertionError(name)
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            self.send_response(200)
            if self.path=='/download':
                self.send_header('Content-Disposition','attachment; filename=synthetic.txt');self.end_headers();self.wfile.write(b'luda-owned-download-sentinel');return
            self.send_header('Content-Type','text/html; charset=utf-8');self.end_headers();self.wfile.write(HTML.encode())
        def do_POST(self):
            value=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            with lock:state.clear();state.update(value)
            (OUT/'oracle.json').write_text(json.dumps(value,ensure_ascii=False,indent=2))
            self.send_response(204);self.end_headers()
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
    async def oracle(expected):
        deadline=time.monotonic()+2
        while True:
            with lock:value=dict(state)
            if value.get('text')==expected:return value
            if time.monotonic()>deadline:return value
            await asyncio.sleep(.03)
    params=StdioServerParameters(command=str(ROOT/'.venv/bin/luda'),env=dict(os.environ,LUDA_CHROMIUM_EXECUTABLE=executable,GTK_IM_MODULE="simple"))
    browser_pid=None;profile=None
    try:
        async with stdio_client(params) as streams:
            async with ClientSession(*streams) as session:
                await session.initialize()
                async def call(tool,**kw):
                    r=await session.call_tool(tool,kw);v=json.loads(r.content[0].text)
                    if r.isError:raise AssertionError((tool,v))
                    return v
                async def error(name,code,**kw):
                    r=await session.call_tool(name,kw);v=json.loads(r.content[0].text)
                    record(name+'-'+code,r.isError and v['code']==code,v);return v
                opened=await call('desktop_open_browser',url=f'http://127.0.0.1:{server.server_port}',lifetime='temporary_session')
                record('explicit-temporary-lifetime',opened['unsaved_content_survives_disconnect'] is False,opened)
                wid=opened['window_id'];await call('desktop_activate',window_id=wid)
                ws=await call('desktop_windows');browser_pid=next(w['pid'] for w in ws['windows'] if w['window_id']==wid)
                # Trace only the owned browser's actual ancestor chain, not global names.
                pid=browser_pid
                while pid>1:
                    raw=(Path('/proc')/str(pid)/'cmdline').read_bytes().split(b'\0')
                    if b'luda._browser_worker' in raw:profile=Path(raw[-2].decode())
                    tail=(Path('/proc')/str(pid)/'stat').read_text().rsplit(')',1)[1].split();pid=int(tail[1])
                async def field(name):
                    tree=await call('desktop_inspect',window_id=wid,name=name)
                    found=[f for f in tree.get('text_fields',[]) if f['name']==name]
                    if len(found)!=1:raise AssertionError(tree)
                    return found[0]['element_id']
                eid=await field('Exact field')
                payload='A👩🏽‍💻B\n\t日本語 é\n\n'
                typed=await call('desktop_type',element_id=eid,text=payload,mode='replace')
                actual=await oracle(payload)
                record('exact-multiline-native-input',typed['exact_match'] and actual.get('text')==payload,actual)
                record('native-input-events',any(e['type']=='beforeinput' and e['inputType']=='insertText' and e['trusted'] for e in actual['events']),actual['events'])
                read=await call('desktop_read_text',element_id=eid);record('exact-read-codepoints',read['text']==payload and read['characters']==len(payload),read)
                await call('desktop_select',element_id=eid,start_offset=1,end_offset=5)
                await call('desktop_type',element_id=eid,text='X')
                expected=payload[:1]+'X'+payload[5:];actual=await oracle(expected)
                record('astral-selection-replacement',actual.get('text')==expected,actual)
                single=await field('Single field')
                await call('desktop_type',element_id=single,text='leading 001😀',mode='replace')
                cleared=await call('desktop_type',element_id=single,text='',mode='replace')
                deadline=time.monotonic()+2
                while state.get('single')!='' and time.monotonic()<deadline:await asyncio.sleep(.02)
                record('empty-replacement-native-delete',cleared['exact_match'] and state.get('single')=='')
                secret=await field('Protected field');denied=await error('desktop_read_text','PROTECTED_FIELD',element_id=secret)
                record('protected-response-redacted','synthetic-protected' not in json.dumps(denied))
                async def button(name):
                    tree=await call('desktop_inspect',window_id=wid,name=name)
                    node=next(n for n in tree['nodes'] if n['name']==name and n['role']=='push button')
                    await call('desktop_invoke',element_id=node['element_id'],action='press')
                links=await call('desktop_inspect',window_id=wid,name='Download fixture')
                link=next(n for n in links['nodes'] if n['name']=='Download fixture' and n['role']=='link')
                await call('desktop_invoke',element_id=link['element_id'],action=link['actions'][0])
                deadline=time.monotonic()+2;downloads=[]
                while time.monotonic()<deadline:
                    downloads=[p for p in (profile/'.luda-temporary').rglob('*') if p.is_file() and p.stat().st_size==28 and p.read_bytes()==b'luda-owned-download-sentinel']
                    if downloads:break
                    await asyncio.sleep(.02)
                record('download-owned-by-profile',len(downloads)==1,[str(p.relative_to(profile)) for p in downloads])
                await button('Replace field');await asyncio.sleep(.1)
                await error('desktop_type','STALE_TARGET',element_id=eid,text='must not appear')
                eid=await field('Exact field');await call('desktop_focus_element',element_id=eid)
                await call('desktop_press_keys',window_id=wid,chord='ctrl+shift+u')
                for key in ('3','0','6','b'):await call('desktop_press_keys',window_id=wid,chord=key)
                await asyncio.sleep(.1)
                shot=await session.call_tool('desktop_observe',{})
                for block in shot.content:
                    if block.type=='image':(OUT/'ime-screen.png').write_bytes(base64.b64decode(block.data))
                before_ime=await call('desktop_read_text',element_id=eid)
                with lock:ime_oracle=dict(state)
                record('native-ime-precondition',before_ime['composition']['active'] and any(e['type']=='compositionstart' and e['trusted'] for e in ime_oracle['events']),{'read':before_ime,'oracle':ime_oracle})
                await error('desktop_type','IME_COMPOSITION_ACTIVE',element_id=eid,text='must not replace preedit')
                await asyncio.sleep(.1)
                record('preedit-preserved-after-refusal',state.get('text')==before_ime['text'])
                await call('desktop_press_keys',window_id=wid,chord='Escape')
                await button('Reload document');await asyncio.sleep(.15)
                await error('desktop_read_text','STALE_TARGET',element_id=eid)
                await button('Add frame')
                deadline=time.monotonic()+2
                while state.get('frames')!=1 and time.monotonic()<deadline:await asyncio.sleep(.02)
                record('frame-present-independent-oracle',state.get('frames')==1,dict(state))
                await error('desktop_inspect','BROWSER_SCOPE_UNSUPPORTED',window_id=wid)
        deadline=time.monotonic()+5
        while time.monotonic()<deadline and (Path('/proc',str(browser_pid)).exists() or profile and profile.exists()):await asyncio.sleep(.05)
        record('disconnect-closes-browser',not Path('/proc',str(browser_pid)).exists())
        record('disconnect-deletes-owned-profile',profile is not None and not profile.exists(),str(profile))
        # Real browser fault cases, each with a fresh MCP server and profile.
        # Record exact descendants before injecting the fault; no name-based kills.
        import live_mcp_disconnect as wire
        wire.OUT=OUT
        with patch.dict(os.environ,LUDA_CHROMIUM_EXECUTABLE=executable,GTK_IM_MODULE='simple'):
            for fault in ('guardian-stopped','server-killed','worker-killed'):
                client=await wire.Client(fault).start()
                guardian=worker=None
                try:
                    opened=await client.call('desktop_open_browser',url=f'http://127.0.0.1:{server.server_port}',lifetime='temporary_session')
                    owned=wire.process_identities(client.process.pid)
                    for pid in owned:
                        try:args=Path('/proc',str(pid),'cmdline').read_bytes().split(b'\0')
                        except FileNotFoundError:continue
                        if b'luda._browser_guard' in args:guardian=pid
                        if b'luda._browser_worker' in args:worker=pid;fault_profile=Path(args[-2].decode())
                    record(fault+'-ownership-precondition',guardian is not None and worker is not None and fault_profile.exists())
                    began=time.monotonic()
                    if fault=='guardian-stopped':
                        os.kill(guardian,signal.SIGSTOP);await client.eof();await client.exited()
                    elif fault=='server-killed':
                        client.process.kill();await client.exited()
                    else:
                        os.kill(worker,signal.SIGKILL)
                    deadline=time.monotonic()+5
                    while time.monotonic()<deadline and (wire.alive(owned) or fault_profile.exists()):await asyncio.sleep(.03)
                    record(fault+'-owned-cleanup',not wire.alive(owned) and not fault_profile.exists(),{'survivors':wire.alive(owned),'profile_exists':fault_profile.exists(),'seconds':round(time.monotonic()-began,3)})
                finally:
                    if guardian:
                        try:os.kill(guardian,signal.SIGCONT)
                        except ProcessLookupError:pass
                    await client.close()

    finally:
        server.shutdown();server.server_close()
    return 0


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--executable',required=True)
    raise SystemExit(asyncio.run(main(parser.parse_args().executable)))
