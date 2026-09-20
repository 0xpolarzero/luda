import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[3]/"tests"))
"""Actual MCP cooperating ProseMirror input with independent application model oracle."""
import argparse,asyncio,http.server,json,os,threading,time
from pathlib import Path
from unittest.mock import patch
import live_mcp_disconnect as wire
from cancellation_finalization import finalized_cancellation
ROOT=Path(__file__).resolve().parents[3];OUT=ROOT/'artifacts/owned-rich-clipboard';ASSETS=ROOT/'addons/editor-bridge/tests/fixtures/pm-selection'


async def main(executable):
    if os.getuid()==0 or os.environ.get('LUDA_ISOLATED_TEST_DISPLAY')!='1':raise RuntimeError('Private ordinary-account desktop required')
    OUT.mkdir(parents=True,exist_ok=True);wire.OUT=OUT;state={};rows=[];lock=threading.Lock()
    barrier_entered=threading.Event();barrier_release=threading.Event();barrier_state={}
    started=time.monotonic();request_count=0
    def timing(**value):
        with (OUT/'timings.jsonl').open('a') as stream:stream.write(json.dumps({'elapsed':round(time.monotonic()-started,3),**value})+'\n')
    (OUT/'timings.jsonl').write_text('')
    def record(case,passed,**details):
        timing(event='case',case=case,passed=bool(passed));rows.append(dict(case=case,passed=bool(passed),**details));(OUT/'results.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
        if not passed:raise AssertionError(case)
    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            name=self.path.split('?')[0]
            path=ROOT/'addons/editor-bridge/application/luda-prosemirror.mjs' if name=='/bridge.mjs' else ASSETS/('index.html' if name=='/' else name.lstrip('/'))
            if path.parent not in (ASSETS,ROOT/'addons/editor-bridge/application') or not path.is_file():self.send_error(404);return
            data=path.read_bytes();self.send_response(200);self.send_header('Content-Type','text/javascript' if path.suffix in ('.js','.mjs') else 'text/html; charset=utf-8');self.end_headers();self.wfile.write(data)
        def do_POST(self):
            value=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
            if self.path=='/cancel-barrier':
                barrier_state.update(value)
                (OUT/'cancel-barrier-oracle.json').write_text(json.dumps(value,ensure_ascii=False,indent=2))
                barrier_entered.set()
                barrier_release.wait(12)  # Independently bounded even if the client fails.
            else:
                with lock:state.clear();state.update(value)
            (OUT/'oracle.json').write_text(json.dumps(value,ensure_ascii=False,indent=2));self.send_response(204);self.end_headers()
    service=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=service.serve_forever,daemon=True).start()
    async def wait(predicate):
        end=time.monotonic()+2
        while not predicate() and time.monotonic()<end:await asyncio.sleep(.02)
        return predicate()
    # GTK's canonical built-in ID; 'simple' can fall back to an installed IBus module.
    with patch.dict(os.environ,LUDA_CHROMIUM_EXECUTABLE=executable,GTK_IM_MODULE='gtk-im-context-simple'):
        client=await wire.Client('mcp', command=str(ROOT/'.venv/bin/luda-editor-bridge')).start()
        request=client.request
        async def traced_request(method,params):
            nonlocal request_count
            request_count+=1;identifier=request_count;begin=time.monotonic()
            timing(event='request_start',index=identifier,tool=params.get('name'),method=method)
            try:
                response=await asyncio.wait_for(request(method,params),16)  # Includes request write/drain as well as its15s reply bound.
                content=response.get('result',{}).get('content',[])
                value=json.loads(content[0]['text']) if content and content[0].get('type')=='text' else {}
                timing(event='request_end',index=identifier,seconds=round(time.monotonic()-begin,3),code=value.get('code'),backend_ms=value.get('elapsed_ms'))
                return response
            except BaseException as exc:
                timing(event='request_exception',index=identifier,seconds=round(time.monotonic()-begin,3),exception=type(exc).__name__)
                raise
        client.request=traced_request
        async def call(tool,**arguments):
            response=(await client.request('tools/call',{'name':tool,'arguments':arguments}))['result']
            value=json.loads(response['content'][0]['text'])
            if response.get('isError'):raise AssertionError((tool,value))
            return value
        try:
            opened=await call('editor_open',url=f'http://127.0.0.1:{service.server_port}',lifetime='temporary_session');wid=opened['window_id']
            await call('editor_activate',window_id=wid);await wait(lambda:state.get('model') is not None)
            async def field():
                tree=await call('editor_inspect',window_id=wid,name='Observed rich editor')
                fields=tree.get('text_fields',[])
                if len(fields)!=1:raise AssertionError(tree)
                return fields[0]['element_id']
            async def button(name):
                tree=await call('editor_inspect',window_id=wid,name=name)
                node=next(n for n in tree['nodes'] if n['role']=='push button' and n['name']==name)
                await call('editor_invoke',element_id=node['element_id'],action='press')
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
                await call('editor_type',element_id=eid,text=initial,mode='replace',line_breaks='paragraph')
                await call('editor_focus',element_id=eid)
                if seed=='marks':
                    await call('editor_select',element_id=eid,start_offset=0,end_offset=4)
                    await call('editor_press_keys',window_id=wid,chord='ctrl+b')
                    await call('editor_select',element_id=eid,start_offset=12,end_offset=17)
                    await call('editor_press_keys',window_id=wid,chord='ctrl+i')
                await call('editor_select',element_id=eid,start_offset=start,end_offset=end)
                old=await call('editor_read',element_id=eid)
                result=await call('editor_type',element_id=eid,text=text,transport='clipboard',line_breaks='paragraph')
                expected=initial[:start]+text+initial[end:]
                await wait(lambda:state.get('modelText')==expected)
                record(name,result['exact_match'] and state['modelText']==expected and state['model']==result['model'],result=result,before=old,oracle=dict(state))
            from luda.common import run
            record('clipboard-remains-final-segment',run(['xclip','-selection','clipboard','-out']).decode()=='new')
            eid=await fresh();await call('editor_focus',element_id=eid)
            await call('editor_select',element_id=eid,start_offset=2,end_offset=4)
            await denied('editor_type','UNSUPPORTED_SELECTION',element_id=eid,text='x')
            before=await call('editor_read',element_id=eid)
            denied_result=await denied('editor_type','LINE_BREAK_SEMANTICS_REQUIRED',element_id=eid,text='a\nb',transport='clipboard')
            after=await call('editor_read',element_id=eid)
            record('policy-refusal-before-mutation',denied_result['effect']=='none' and before['model']==after['model'])
            original=eid;await button('Renew registration')
            await denied('editor_select','STALE_TARGET',element_id=original,start_offset=0,end_offset=1)
            eid=await field();await button('Load 128 paragraphs');await wait(lambda:len(state['model']['content'])==128)
            await call('editor_focus',element_id=eid);await call('editor_select',element_id=eid,start_offset=127,end_offset=127)
            limit_before=json.loads(json.dumps(state['model']));clipboard_before=run(['xclip','-selection','clipboard','-out'])
            limit=await denied('editor_type','VERIFICATION_LIMIT',element_id=eid,text='\n',transport='clipboard',line_breaks='paragraph')
            record('predicted-paragraph-limit-preserves-clipboard',limit['effect']=='none' and state['model']==limit_before and run(['xclip','-selection','clipboard','-out'])==clipboard_before)
            # Native Ctrl+End legitimately scrolls the 128-paragraph editor.
            # Return the viewport to its controls before requesting a reset.
            await call('editor_press_keys',window_id=wid,chord='ctrl+Home')
            shot=await call('editor_observe');bounds=next(w['image_bounds'] for w in shot['windows'] if w['window_id']==wid)
            await call('editor_scroll',window_id=wid,snapshot_id=shot['snapshot_id'],x=bounds['x']+bounds['width']/2,y=bounds['y']+bounds['height']/2,direction='up',ticks=5)
            record('scroll-preserves-limit-model',state['model']==limit_before)
            eid=await fresh();await call('editor_focus',element_id=eid);await call('editor_select',element_id=eid,start_offset=2,end_offset=4)
            clipboard_before=run(['xclip','-selection','clipboard','-out'])
            run(['xdotool','keydown','Shift_L'])
            try:
                held=await denied('editor_type','INPUT_HELD',element_id=eid,text='held refusal',transport='clipboard')
                record('held-input-preserves-clipboard',held['effect']=='none' and run(['xclip','-selection','clipboard','-out'])==clipboard_before)
            finally:run(['xdotool','keyup','Shift_L'])
            await button('Move focus after next input')
            failed=await denied('editor_type','FOCUS_CHANGED',element_id=eid,text='first\nsecond',transport='clipboard',line_breaks='paragraph')
            await asyncio.sleep(.2)
            record('paste-focus-loss-stops-remainder',failed['effect']=='uncertain' and failed.get('details',{}).get('clipboard_may_have_changed') and 'second' not in state['modelText'],oracle=dict(state))
            eid=await fresh();await call('editor_focus',element_id=eid)
            await call('editor_press_keys',window_id=wid,chord='ctrl+shift+u')
            for key in ('3','0','6','b'):await call('editor_press_keys',window_id=wid,chord=key)
            await asyncio.sleep(.1);ime_before=json.loads(json.dumps(state));clipboard_before=run(['xclip','-selection','clipboard','-out'])
            ime=await denied('editor_type','IME_COMPOSITION_ACTIVE',element_id=eid,text='must refuse',mode='replace',transport='clipboard')
            record('trusted-preedit-preserved',ime['effect']=='none' and state['model']==ime_before['model'] and any(e['type']=='compositionstart' and e['trusted'] for e in ime_before['events']) and run(['xclip','-selection','clipboard','-out'])==clipboard_before)
            await call('editor_press_keys',window_id=wid,chord='Escape')
            document_id=state['documentId'];await button('Reload document');await wait(lambda:state['documentId']!=document_id)
            eid=await field();await call('editor_type',element_id=eid,text='',mode='replace')
            record('cancel-empty-baseline',await wait(lambda:state.get('modelText')==''))
            await button('Arm cancellation barrier')
            baseline=await call('editor_status')
            prior_ids={event['operation_id'] for event in baseline['operations']}
            owned=wire.process_identities(client.process.pid)
            # Cancellation closes the browser, while the MCP session (including
            # its cursor overlay) remains available for explicit recovery.
            guards=[pid for pid in owned if b'luda_editor_bridge.guard' in Path('/proc',str(pid),'cmdline').read_bytes().split(b'\0')]
            record('cancel-browser-ownership',len(guards)==1)
            all_owned=owned
            owned={guards[0]:all_owned[guards[0]],**wire.process_identities(guards[0])}
            payload='\n'.join('segment-'+str(i) for i in range(27))
            pending=await client.begin('tools/call',{'name':'editor_type','arguments':{'element_id':eid,'text':payload,'line_breaks':'paragraph','transport':'clipboard'}})
            request_id=client.next_id
            try:
                entered=await asyncio.to_thread(barrier_entered.wait,5)
                record('cancel-after-independent-first-input',entered and barrier_state.get('modelText')=='segment-0' and not pending.done(),oracle=dict(barrier_state),response=pending.result() if pending.done() else None)
                await client.send({'jsonrpc':'2.0','method':'notifications/cancelled','params':{'requestId':request_id,'reason':'synthetic bounded cancellation'}})
                deadline=time.monotonic()+8
                while wire.alive(owned) and time.monotonic()<deadline:await asyncio.sleep(.05)
                record('cancel-owned-browser-processes-closed',not wire.alive(owned),survivors=wire.alive(owned),response=pending.result() if pending.done() else None)
            finally:barrier_release.set()
            try:
                cancelled_response=await asyncio.wait_for(asyncio.shield(pending),3)
            except asyncio.TimeoutError:
                record('cancel-response-received',False,response=None)
            record('cancel-response-received',cancelled_response.get('id')==request_id and 'error' in cancelled_response,response=cancelled_response)
            deadline=time.monotonic()+5;finalized=None;final_status=None
            while time.monotonic()<deadline:
                final_status=await call('editor_status')
                finalized=finalized_cancellation(final_status,prior_ids)
                if finalized:break
                await asyncio.sleep(.02)
            record('cancel-operation-finalized',finalized is not None,status=final_status)
            partial=barrier_state.get('modelText')
            record('cancel-stops-without-replay',partial=='segment-0' and partial!=payload,partial=partial)
            document_id=state['documentId'];opened=await call('editor_open',url=f'http://127.0.0.1:{service.server_port}',lifetime='temporary_session');wid=opened['window_id']
            await call('editor_activate',window_id=wid);await wait(lambda:state['documentId']!=document_id)
            record('fresh-session-no-replay',state['modelText']==seeds['plain'])
            eid=await field();recovered=await call('editor_type',element_id=eid,text='explicit recovery',mode='replace',transport='clipboard')
            await wait(lambda:state['modelText']=='explicit recovery');record('explicit-recovery-new-request',recovered['exact_match'] and state['modelText']=='explicit recovery')
            all_owned.update(wire.process_identities(client.process.pid))
        finally:barrier_release.set();await client.close();service.shutdown();service.server_close()
        deadline=time.monotonic()+5
        while wire.alive(all_owned) and time.monotonic()<deadline:await asyncio.sleep(.05)
        record('disconnect-closes-all-session-processes',not wire.alive(all_owned),survivors=wire.alive(all_owned))
    return 0

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--executable',required=True)
    raise SystemExit(asyncio.run(main(p.parse_args().executable)))
