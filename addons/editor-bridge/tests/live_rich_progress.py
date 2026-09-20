import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/"tests"))
"""First paragraph verified, second refused by a real application key handler."""
import argparse,asyncio,http.server,json,os,threading,time
from pathlib import Path
from unittest.mock import patch
import live_mcp_disconnect as wire
ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/'artifacts/rich-progress'
ASSETS=ROOT/'addons/editor-bridge/tests/fixtures/owned-rich-editor'
GUARD=b"""window.addEventListener('keydown',e=>{if(e.isTrusted&&e.key==='Enter'&&e.target.closest('.ProseMirror')){e.preventDefault();e.stopImmediatePropagation();fetch('/blocked',{method:'POST',body:'1'});}},true);"""

async def main(executable):
    if os.getuid()==0 or os.environ.get('LUDA_ISOLATED_TEST_DISPLAY')!='1':raise RuntimeError('Private ordinary-account desktop required')
    OUT.mkdir(parents=True,exist_ok=True);wire.OUT=OUT;state={};blocked=0;rows=[]
    def record(case,passed,**details):
        rows.append(dict(case=case,passed=bool(passed),**details));(OUT/'results.json').write_text(json.dumps(rows,indent=2))
        if not passed:raise AssertionError(case)
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            if self.path=='/guard.js':body=GUARD;mime='text/javascript'
            elif self.path=='/bridge.mjs':body=(ROOT/'addons/editor-bridge/application/luda-prosemirror.mjs').read_bytes();mime='text/javascript'
            elif self.path=='/':body=(ASSETS/'index.html').read_bytes()+b'<script src="/guard.js"></script>';mime='text/html'
            elif self.path=='/editor.bundle.js':body=(ASSETS/'editor.bundle.js').read_bytes();mime='text/javascript'
            else:self.send_error(404);return
            self.send_response(200);self.send_header('Content-Type',mime+'; charset=utf-8');self.end_headers();self.wfile.write(body)
        def do_POST(self):
            nonlocal blocked
            data=self.rfile.read(int(self.headers['Content-Length']))
            if self.path=='/blocked':blocked+=1
            elif self.path=='/oracle':state.clear();state.update(json.loads(data))
            else:self.send_error(404);return
            self.send_response(204);self.end_headers()
    service=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=service.serve_forever,daemon=True).start()
    try:
        for transport in ('native','clipboard'):
            state.clear();blocked=0
            with patch.dict(os.environ,LUDA_CHROMIUM_EXECUTABLE=executable,GTK_IM_MODULE='gtk-im-context-simple'):
                client=await wire.Client(transport, command=str(ROOT/'.venv/bin/luda-editor-bridge')).start()
            async def call(tool,**arguments):
                result=(await client.request('tools/call',{'name':tool,'arguments':arguments}))['result']
                return result,json.loads(result['content'][0]['text'])
            try:
                _,opened=await call('editor_open',url=f'http://127.0.0.1:{service.server_port}/',lifetime='temporary_session');wid=opened['window_id']
                await call('editor_activate',window_id=wid)
                deadline=time.monotonic()+3
                while state.get('modelText') is None and time.monotonic()<deadline:await asyncio.sleep(.02)
                _,tree=await call('editor_inspect',window_id=wid,name='Observed rich editor')
                eid=tree['text_fields'][0]['element_id']
                response,error=await call('editor_type',element_id=eid,text='FIRST_PRIVATE\nSECOND_PRIVATE\nTHIRD_PRIVATE',line_breaks='paragraph',transport=transport)
                deadline=time.monotonic()+2
                while (state.get('modelText')!='FIRST_PRIVATE' or blocked!=1) and time.monotonic()<deadline:await asyncio.sleep(.02)
                expected=dict(unit='rich_text_segment',requested=3,verified_completed=1,current_uncertain=1,not_started=1,application_commit_verified=False)
                record(transport+'-partial-progress',response.get('isError') and error['code']=='TEXT_MISMATCH' and error['effect']=='uncertain' and error['details']['progress']==expected,error=error)
                record(transport+'-independent-application-state',state.get('modelText')=='FIRST_PRIVATE' and blocked==1 and len(state['model']['content'])==1,model=state.get('model'),blocked=blocked)
                _,status=await call('editor_status');_,report=await call('editor_report')
                for output in (error,status,report):
                    encoded=json.dumps(output)
                    record(transport+'-payload-free-'+str(len(rows)),all(word not in encoded for word in ('FIRST_PRIVATE','SECOND_PRIVATE','THIRD_PRIVATE')))
                history=status['operations']
                record(transport+'-history-progress',any(e.get('progress')==expected for e in history))
            finally:
                await client.close();record(transport+'-clean-exit',client.process.returncode==0 and not client.forced_shutdown)
    finally:service.shutdown();service.server_close()
    return 0
if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--executable',required=True)
    raise SystemExit(asyncio.run(main(parser.parse_args().executable)))
