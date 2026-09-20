"""Actual MCP cooperating ProseMirror input with independent application model oracle."""
import argparse,asyncio,http.server,json,os,threading,time
from pathlib import Path
from unittest.mock import patch
import live_mcp_disconnect as wire
from live_rich_editor import SAMPLES
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts/owned-rich-clipboard';ASSETS=ROOT/'tests/fixtures/pm-selection'


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
            from live_pm_selection import CASES
            seeds={'plain':'A👩🏽‍💻B éC','paragraphs':'first\n\nlast','marks':'LEFT middle RIGHT','empty':'','boundaries':'AB\nCD\nEF'}
            for name,seed,start,end,text,backward in CASES+[('delete-inside-zwj','plain',2,4,'',False),('delete-accent','plain',8,9,'',False),('delete-base-before-accent','plain',7,8,'',False),('delete-whole-emoji','plain',1,5,'',False)]:
                eid=await fresh();initial=seeds[seed]
                await call('desktop_type',element_id=eid,text=initial,mode='replace',line_breaks='paragraph')
                await call('desktop_focus_element',element_id=eid)
                if seed=='marks':
                    await call('desktop_select',element_id=eid,start_offset=0,end_offset=4)
                    await call('desktop_press_keys',window_id=wid,chord='ctrl+b')
                    await call('desktop_select',element_id=eid,start_offset=12,end_offset=17)
                    await call('desktop_press_keys',window_id=wid,chord='ctrl+i')
                await call('desktop_select',element_id=eid,start_offset=start,end_offset=end)
                old=await call('desktop_read_text',element_id=eid)
                result=await call('desktop_type',element_id=eid,text=text,transport='clipboard',line_breaks='paragraph')
                expected=initial[:start]+text+initial[end:]
                await wait(lambda:state.get('modelText')==expected)
                record(name,result['exact_match'] and state['modelText']==expected and state['model']==result['model'],result=result,before=old,oracle=dict(state))
            from luda.common import run
            record('clipboard-remains-final-segment',run(['xclip','-selection','clipboard','-out']).decode()=='new')
            eid=await fresh();await call('desktop_focus_element',element_id=eid)
            await call('desktop_select',element_id=eid,start_offset=2,end_offset=4)
            await denied('desktop_type','UNSUPPORTED_SELECTION',element_id=eid,text='x')
            before=await call('desktop_read_text',element_id=eid)
            denied_result=await denied('desktop_type','LINE_BREAK_SEMANTICS_REQUIRED',element_id=eid,text='a\nb',transport='clipboard')
            after=await call('desktop_read_text',element_id=eid)
            record('policy-refusal-before-mutation',denied_result['effect']=='none' and before['model']==after['model'])
            original=eid;await button('Renew registration')
            await denied('desktop_select','STALE_TARGET',element_id=original,start_offset=0,end_offset=1)
            eid=await field();await button('Load 128 paragraphs');await wait(lambda:len(state['model']['content'])==128)
            await call('desktop_focus_element',element_id=eid);await call('desktop_select',element_id=eid,start_offset=127,end_offset=127)
            limit_before=json.loads(json.dumps(state['model']));clipboard_before=run(['xclip','-selection','clipboard','-out'])
            limit=await denied('desktop_type','VERIFICATION_LIMIT',element_id=eid,text='\n',transport='clipboard',line_breaks='paragraph')
            record('predicted-paragraph-limit-preserves-clipboard',limit['effect']=='none' and state['model']==limit_before and run(['xclip','-selection','clipboard','-out'])==clipboard_before)
            eid=await fresh();await call('desktop_focus_element',element_id=eid);await call('desktop_select',element_id=eid,start_offset=2,end_offset=4)
            clipboard_before=run(['xclip','-selection','clipboard','-out'])
            run(['xdotool','keydown','Shift_L'])
            try:
                held=await denied('desktop_type','INPUT_HELD',element_id=eid,text='held refusal',transport='clipboard')
                record('held-input-preserves-clipboard',held['effect']=='none' and run(['xclip','-selection','clipboard','-out'])==clipboard_before)
            finally:run(['xdotool','keyup','Shift_L'])
            await button('Move focus after next input')
            failed=await denied('desktop_type','FOCUS_CHANGED',element_id=eid,text='first\nsecond',transport='clipboard',line_breaks='paragraph')
            await asyncio.sleep(.2)
            record('paste-focus-loss-stops-remainder',failed['effect']=='uncertain' and failed.get('details',{}).get('clipboard_may_have_changed') and 'second' not in state['modelText'],oracle=dict(state))
            eid=await fresh();await call('desktop_focus_element',element_id=eid)
            await call('desktop_press_keys',window_id=wid,chord='ctrl+shift+u')
            for key in ('3','0','6','b'):await call('desktop_press_keys',window_id=wid,chord=key)
            await asyncio.sleep(.1);ime_before=json.loads(json.dumps(state));clipboard_before=run(['xclip','-selection','clipboard','-out'])
            ime=await denied('desktop_type','IME_COMPOSITION_ACTIVE',element_id=eid,text='must refuse',mode='replace',transport='clipboard')
            record('trusted-preedit-preserved',ime['effect']=='none' and state['model']==ime_before['model'] and any(e['type']=='compositionstart' and e['trusted'] for e in ime_before['events']) and run(['xclip','-selection','clipboard','-out'])==clipboard_before)
            await call('desktop_press_keys',window_id=wid,chord='Escape')
            document_id=state['documentId'];await button('Reload document');await wait(lambda:state['documentId']!=document_id)
            eid=await field();await call('desktop_type',element_id=eid,text='',mode='replace')
            payload='\n'.join('segment-'+str(i) for i in range(27))
            pending=await client.begin('tools/call',{'name':'desktop_type','arguments':{'element_id':eid,'text':payload,'line_breaks':'paragraph','transport':'clipboard'}})
            request_id=client.next_id
            await wait(lambda:bool(state['modelText']))
            record('cancel-after-independent-first-input',bool(state['modelText']) and not pending.done())
            await client.send({'jsonrpc':'2.0','method':'notifications/cancelled','params':{'requestId':request_id,'reason':'synthetic bounded cancellation'}})
            await asyncio.sleep(.5);partial=state['modelText'];await asyncio.sleep(.3)
            record('cancel-stops-without-replay',payload.startswith(partial) and partial!=payload and state['modelText']==partial,partial=partial)
            document_id=state['documentId'];opened=await call('desktop_open_browser',url=f'http://127.0.0.1:{service.server_port}',lifetime='temporary_session');wid=opened['window_id']
            await call('desktop_activate',window_id=wid);await wait(lambda:state['documentId']!=document_id)
            record('fresh-session-no-replay',state['modelText']==seeds['plain'])
            eid=await field();recovered=await call('desktop_type',element_id=eid,text='explicit recovery',mode='replace',transport='clipboard')
            await wait(lambda:state['modelText']=='explicit recovery');record('explicit-recovery-new-request',recovered['exact_match'] and state['modelText']=='explicit recovery')
        finally:await client.close();service.shutdown();service.server_close()
    return 0

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--executable',required=True)
    raise SystemExit(asyncio.run(main(p.parse_args().executable)))
