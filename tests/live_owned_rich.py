"""Actual MCP cooperating ProseMirror input with independent application model oracle."""
import argparse,asyncio,http.server,json,os,threading,time
from pathlib import Path
from unittest.mock import patch
import live_mcp_disconnect as wire
from live_rich_editor import SAMPLES
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts/owned-rich';ASSETS=ROOT/'tests/fixtures/owned-rich-editor'


async def main(executable):
    if os.getuid()==0 or os.environ.get('LUDA_ISOLATED_TEST_DISPLAY')!='1':raise RuntimeError('Private ordinary-account desktop required')
    OUT.mkdir(parents=True,exist_ok=True);wire.OUT=OUT;state={};rows=[];lock=threading.Lock()
    def record(case,passed,**details):
        rows.append(dict(case=case,passed=bool(passed),**details));(OUT/'results.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
        if not passed:raise AssertionError(case)
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            name=self.path.split('?')[0]
            path=ROOT/'integrations/prosemirror/luda-prosemirror.mjs' if name=='/bridge.mjs' else ASSETS/('index.html' if name=='/' else name.lstrip('/'))
            if path.parent not in (ASSETS,ROOT/'integrations/prosemirror') or not path.is_file():self.send_error(404);return
            data=path.read_bytes();self.send_response(200);self.send_header('Content-Type','text/javascript' if path.suffix in ('.js','.mjs') else 'text/html; charset=utf-8');self.end_headers();self.wfile.write(data)
        def do_POST(self):
            value=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            with lock:state.clear();state.update(value)
            (OUT/'oracle.json').write_text(json.dumps(value,ensure_ascii=False,indent=2));self.send_response(204);self.end_headers()
    service=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=service.serve_forever,daemon=True).start()
    async def wait(predicate):
        end=time.monotonic()+2
        while not predicate() and time.monotonic()<end:await asyncio.sleep(.02)
        return predicate()
    with patch.dict(os.environ,LUDA_CHROMIUM_EXECUTABLE=executable,GTK_IM_MODULE='simple'):
        client=await wire.Client('mcp').start()
        async def call(tool,**arguments):
            response=(await client.request('tools/call',{'name':tool,'arguments':arguments}))['result']
            value=json.loads(response['content'][0]['text'])
            if response.get('isError'):raise AssertionError((tool,value))
            return value
        try:
            opened=await call('desktop_open_browser',url=f'http://127.0.0.1:{service.server_port}',lifetime='temporary_session');wid=opened['window_id']
            await call('desktop_activate',window_id=wid);await wait(lambda:state.get('model') is not None)
            async def field():
                tree=await call('desktop_inspect',window_id=wid,name='Observed rich editor')
                fields=tree.get('text_fields',[])
                if len(fields)!=1:raise AssertionError(tree)
                return fields[0]['element_id']
            async def button(name):
                tree=await call('desktop_inspect',window_id=wid,name=name)
                node=next(n for n in tree['nodes'] if n['role']=='push button' and n['name']==name)
                await call('desktop_invoke',element_id=node['element_id'],action='press')
            async def fresh():
                generation=state['generation'];await button('Replace editor node');await wait(lambda:state['generation']>generation)
                return await field()
            async def denied(tool,code,**kwargs):
                r=(await client.request('tools/call',{'name':tool,'arguments':kwargs}))['result'];v=json.loads(r['content'][0]['text'])
                record(tool+'-'+code,r.get('isError') and v['code']==code,response=v);return v
            for name,payload in SAMPLES:
                if name=='crlf':continue
                eid=await fresh()
                result=await call('desktop_type',element_id=eid,text=payload,mode='replace',line_breaks='paragraph')
                await wait(lambda:state.get('modelText')==payload)
                record('paragraph-'+name,result['exact_match'] and state['modelText']==payload and state['model']==result['model'],result=result,oracle=dict(state))
            eid=await fresh();await call('desktop_focus_element',element_id=eid)
            await call('desktop_press_keys',window_id=wid,chord='ctrl+b')
            await call('desktop_type',element_id=eid,text='BOLD 😀')
            old_model=json.loads(json.dumps(state['model']))
            result=await call('desktop_type',element_id=eid,text='\nplain\n',line_breaks='paragraph')
            await wait(lambda:state['modelText']=='BOLD 😀\nplain\n')
            record('styled-prefix-preserved',result['existing_formatting']=='preserved' and result['model']['content'][0]==old_model['content'][0] and state['model']==result['model'],result=result)
            record('new-formatting-reported-not-forced',result['model']['content'][1]['content'][0].get('marks',[])==[],model=result['model'])
            before=json.loads(json.dumps(state))
            await denied('desktop_type','LINE_BREAK_SEMANTICS_REQUIRED',element_id=eid,text='a\nb')
            record('missing-policy-no-mutation',state['model']==before['model'])
            await call('desktop_press_keys',window_id=wid,chord='Left')
            await denied('desktop_type','UNSUPPORTED_SELECTION',element_id=eid,text='no mid insertion')
            previous=eid;eid=await fresh();await denied('desktop_type','STALE_TARGET',element_id=previous,text='stale')
            await button('Insert image model node')
            await denied('desktop_type','TEXT_REPRESENTATION_UNSUPPORTED',element_id=eid,text='no image replacement',mode='replace')
            eid=await fresh();await button('Arm unsupported link mark')
            pending_mark=await denied('desktop_type','TEXT_REPRESENTATION_UNSUPPORTED',element_id=eid,text='must not insert')
            record('unsupported-stored-mark-no-input',state['modelText']=='' and pending_mark['effect']=='none',oracle=dict(state))
            eid=await fresh();before_model=json.loads(json.dumps(state['model']))
            await button('Renew registration');await denied('desktop_read_text','STALE_TARGET',element_id=eid)
            record('reregister-same-root-preserves-model',state['model']==before_model)
            eid=await field();await button('Move focus after next input')
            failed=await denied('desktop_type','FOCUS_CHANGED',element_id=eid,text='first\nsecond',line_breaks='paragraph')
            await wait(lambda:state['modelText']=='first')
            record('focus-change-stops-after-single-segment',state['modelText']=='first' and failed['effect']=='uncertain',oracle=dict(state))
            eid=await fresh();await call('desktop_focus_element',element_id=eid)
            await call('desktop_press_keys',window_id=wid,chord='ctrl+shift+u')
            for key in ('3','0','6','b'):await call('desktop_press_keys',window_id=wid,chord=key)
            await asyncio.sleep(.1);before=json.loads(json.dumps(state))
            await denied('desktop_type','IME_COMPOSITION_ACTIVE',element_id=eid,text='do not replace preedit',mode='replace')
            record('native-preedit-preserved',state['model']==before['model'] and any(e['type']=='compositionstart' and e['trusted'] for e in before['events']),oracle=before)
            # Explicitly abandon this fixture document after the preedit probe.
            await call('desktop_press_keys',window_id=wid,chord='Escape')
            document_id=state['documentId'];await button('Reload document');await wait(lambda:state['documentId']!=document_id and state['modelText']=='')
            eid=await field();payload='\n'.join('segment-'+str(i) for i in range(27))
            pending=await client.begin('tools/call',{'name':'desktop_type','arguments':{'element_id':eid,'text':payload,'line_breaks':'paragraph'}})
            request_id=client.next_id
            await wait(lambda:bool(state['modelText']))
            record('cancellation-started-before-completion',bool(state['modelText']) and not pending.done(),oracle=dict(state))
            await client.send({'jsonrpc':'2.0','method':'notifications/cancelled','params':{'requestId':request_id,'reason':'synthetic bounded cancellation'}})
            await asyncio.sleep(.4)
            partial=state['modelText'];await asyncio.sleep(.3)
            record('cancellation-does-not-replay-rest',payload.startswith(partial) and partial!=payload and state['modelText']==partial,partial=partial)
            document_id=state['documentId']
            opened=await call('desktop_open_browser',url=f'http://127.0.0.1:{service.server_port}',lifetime='temporary_session');wid=opened['window_id']
            await call('desktop_activate',window_id=wid);await wait(lambda:state['documentId']!=document_id)
            record('explicit-new-session-has-no-replayed-text',state['modelText']=='')
            eid=await field();await call('desktop_type',element_id=eid,text='explicit recovery')
            await wait(lambda:state['modelText']=='explicit recovery');record('explicit-new-request-after-cancellation',state['modelText']=='explicit recovery')
            await button('Load 128 paragraphs');await wait(lambda:len(state['model']['content'])==128)
            await call('desktop_focus_element',element_id=eid)
            await call('desktop_select',element_id=eid,start_offset=127,end_offset=127)
            before_limit=json.loads(json.dumps(state['model']))
            refusal=await denied('desktop_type','VERIFICATION_LIMIT',element_id=eid,text='\n',line_breaks='paragraph')
            record('known-paragraph-limit-refuses-without-input',refusal['effect']=='none' and state['model']==before_limit and len(state['model']['content'])==128)



        finally:await client.close();service.shutdown();service.server_close()
    return 0

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--executable',required=True)
    raise SystemExit(asyncio.run(main(p.parse_args().executable)))
