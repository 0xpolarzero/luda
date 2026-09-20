"""Real Chromium geolocation prompt denial through public MCP; no permission API grants."""
import argparse,asyncio,base64,http.server,json,os,threading,time
from pathlib import Path
from unittest.mock import patch
import live_mcp_disconnect as wire
from permission_oracle import PermissionOracle
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/browser-permission'

class Client(wire.Client):
    async def start(self):
        self.log=(OUT/(self.label+'-stderr.log')).open('w')
        self.process=await asyncio.create_subprocess_exec(str(ROOT/'.venv/bin/luda'),
            stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=self.log,
            start_new_session=True,limit=8*1024*1024)
        self.task=asyncio.create_task(self.read())
        await self.request('initialize',{'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'luda-permission-fixture','version':'1'}})
        await self.send({'jsonrpc':'2.0','method':'notifications/initialized'})
        return self

async def main(executable):
    if os.getuid()==0 or os.environ.get('LUDA_ISOLATED_TEST_DISPLAY')!='1':
        raise RuntimeError('An ordinary UID and private display are required')
    OUT.mkdir(parents=True,exist_ok=True);wire.OUT=OUT
    oracle=PermissionOracle();rows=[];lock=threading.Lock();complete_report=threading.Event()
    def current():
        with lock:return dict(oracle.state)
    def record(case,passed,**details):
        rows.append(dict(case=case,passed=bool(passed),**details))
        (OUT/'results.json').write_text(json.dumps(rows,indent=2))
        if not passed:raise AssertionError(case)
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            if self.path!='/':self.send_error(404);return
            data=(ROOT/'tests/fixtures/browser-permission/index.html').read_bytes()
            self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.end_headers();self.wfile.write(data)
        def do_POST(self):
            if self.path!='/oracle':self.send_error(404);return
            size=int(self.headers['Content-Length'])
            if not 0<size<2048:self.send_error(400);return
            value=json.loads(self.rfile.read(size))
            # Force the first terminal partial report behind its successor.
            # This delays observation transport only, never browser permission input.
            partial=(value.get('permission')=='denied') != (value.get('error')==1)
            if partial:complete_report.wait(timeout=5)
            with lock:
                oracle.accept(value)
                (OUT/'oracle.json').write_text(json.dumps(oracle.state,indent=2))
                (OUT/'oracle-reports.json').write_text(json.dumps(oracle.reports,indent=2))
                if oracle.state.get('permission')=='denied' and oracle.state.get('error')==1:
                    complete_report.set()
            self.send_response(204);self.end_headers()
    service=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
    threading.Thread(target=service.serve_forever,daemon=True).start()
    async def until(predicate,seconds=5):
        deadline=time.monotonic()+seconds
        while time.monotonic()<deadline:
            if predicate():return True
            await asyncio.sleep(.05)
        return bool(predicate())
    client=None
    try:
        with patch.dict(os.environ,LUDA_CHROMIUM_EXECUTABLE=executable):
            client=await Client('permission').start()
        async def call(tool,**arguments):
            result=(await client.request('tools/call',{'name':tool,'arguments':arguments}))['result']
            value=json.loads(result['content'][0]['text'])
            if result.get('isError'):raise RuntimeError(tool+': '+value.get('code','error'))
            return value
        opened=await call('desktop_open_browser',url=f'http://127.0.0.1:{service.server_port}/',lifetime='temporary_session')
        wid=opened['window_id'];await call('desktop_activate',window_id=wid)
        record('fresh-origin-permission-prompt',await until(lambda:current().get('permission')=='prompt'),oracle=current())
        tree=await call('desktop_inspect',window_id=wid,name='Request location')
        buttons=[n for n in tree['nodes'] if n['name']=='Request location' and n['role']=='push button']
        record('observed-request-button',len(buttons)==1)
        record('observed-request-action','press' in buttons[0]['actions'],actions=buttons[0]['actions'])
        await call('desktop_invoke',element_id=buttons[0]['element_id'],action='press')
        record('trusted-request-without-autoaccept',await until(lambda:current().get('requests')==1) and current().get('trustedRequest') and current().get('successes')==0,oracle=current())
        # Only observations repeat while the browser presents its real prompt.
        deadline=time.monotonic()+5;choices=[];trees=[]
        while time.monotonic()<deadline:
            tree=await call('desktop_inspect',window_id=wid,limit=500)
            trees.append(tree)
            choices=[n for n in tree['nodes'] if n['role']=='push button' and n['name'] in ('Never allow','Don’t allow',"Don't allow",'Block')]
            if choices:break
            await asyncio.sleep(.1)
        (OUT/'prompt-trees.json').write_text(json.dumps(trees,indent=2))
        screenshot=(await client.request('tools/call',{'name':'desktop_observe','arguments':{}}))['result']
        for block in screenshot['content']:
            if block['type']=='image':(OUT/'permission-prompt.png').write_bytes(base64.b64decode(block['data']))
        record('real-browser-denial-control-observed',len(choices)==1,choices=[{'name':n['name'],'role':n['role']} for n in choices],oracle=current())
        nodes={n['element_id']:n for n in tree['nodes']}
        ancestor=choices[0];alert=None
        for _ in range(30):
            if ancestor['role']=='alert':alert=ancestor;break
            ancestor=nodes.get(ancestor.get('parent_element_id'))
            if ancestor is None:break
        record('denial-belongs-to-origin-location-alert',alert is not None and alert['name']==f'http://127.0.0.1:{service.server_port} wants to: Know your location',alert_name=alert['name'] if alert else None)
        record('still-awaiting-explicit-denial',current().get('permission')=='prompt' and current().get('error') is None and current().get('successes')==0,oracle=current())
        record('observed-denial-action','press' in choices[0]['actions'],actions=choices[0]['actions'])
        response=await call('desktop_invoke',element_id=choices[0]['element_id'],action='press')
        record('denied-independent-permission-and-callback',await until(lambda:current().get('permission')=='denied' and current().get('error')==1) and current().get('successes')==0 and current().get('requests')==1,response=response,oracle=current())
        record('older-partial-report-cannot-erase-denial',
               await until(lambda:any(not row['applied'] for row in oracle.reports)) and
               current().get('permission')=='denied' and current().get('error')==1,
               oracle=current())
        tree=await call('desktop_inspect',window_id=wid,name='denied')
        (OUT/'after-tree.json').write_text(json.dumps(tree,indent=2))
        record('denied-status-publicly-observed',any('denied' in n.get('name','') for n in tree['nodes']))
    finally:
        if client:
            await client.close()
            record('owned-mcp-clean-exit',not getattr(client,'forced_shutdown',False) and client.process.returncode==0)
        service.shutdown();service.server_close()
    return 0

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--executable',required=True)
    raise SystemExit(asyncio.run(main(parser.parse_args().executable)))
