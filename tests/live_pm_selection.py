"""Prototype public DOM/model range mapping; no production selection API changes."""
import argparse,functools,http.server,json,os,tempfile,threading,time
from pathlib import Path
from unittest.mock import patch
from luda._browser_worker import Worker,Refused
from luda.desktop import Desktop
from pm_selection_probe import SelectionProbe
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts/pm-selection';ASSETS=ROOT/'tests/fixtures/pm-selection'
CASES=[
 ('astral','plain',1,5,'日本語',False),('combining-only','plain',8,9,'x',False),
 ('inside-zwj','plain',2,4,'Z',False),('middle-caret','plain',6,6,'MID',False),
 ('caret-inside-combining','plain',8,8,'x',False),('caret-inside-zwj','plain',2,2,'Q',False),
 ('replace-base-before-combining','plain',7,8,'E',False),('paragraph-inside-grapheme','plain',8,8,'\n',False),
 ('backward-astral','plain',1,5,'R',True),('backward-combining','plain',8,9,'',True),
 ('paragraph-delimiter','boundaries',2,3,'',False),('across-paragraph','boundaries',1,6,'X',False),
 ('multiline-middle','boundaries',1,6,'x\ny\n',False),('leading-lf-middle','boundaries',1,6,'\nx',False),
 ('paragraph-end-caret','boundaries',2,2,'\nM',False),('paragraph-start-caret','boundaries',3,3,'N\n',False),
 ('empty-paragraph-caret','paragraphs',6,6,'EMPTY',False),('empty-paragraph-remove','paragraphs',5,7,'',False),
 ('empty-paragraph-replace','paragraphs',5,7,'\n\n\n',True),('empty-document','empty',0,0,'\n\n',False),
 ('styled-middle','marks',5,11,'new',False),('styled-multiline','marks',5,11,'first\nsecond\n',False),
 ('styled-spacing','marks',5,11,'\t x\u00a0  \n  y\t',False),
 ('inside-bold','marks',1,3,'X',False),('across-marks','marks',2,15,'\nnew\n',True),
]


def main(executable):
    if os.getuid()==0 or os.environ.get('LUDA_ISOLATED_TEST_DISPLAY')!='1':raise RuntimeError('Private ordinary-account desktop required')
    OUT.mkdir(parents=True,exist_ok=True);oracle={};rows=[]
    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self,*args):pass
        def do_GET(self):
            if self.path=='/bridge.mjs':
                body=(ROOT/'integrations/prosemirror/luda-prosemirror.mjs').read_bytes();self.send_response(200);self.send_header('Content-Type','text/javascript');self.end_headers();self.wfile.write(body)
            else:super().do_GET()
        def do_POST(self):
            data=json.loads(self.rfile.read(int(self.headers['Content-Length'])));oracle.clear();oracle.update(data)
            self.send_response(204);self.end_headers()
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(ASSETS)));threading.Thread(target=server.serve_forever,daemon=True).start()
    def record(case,passed,**details):
        rows.append(dict(case=case,passed=bool(passed),**details));(OUT/'results.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2));print(json.dumps({'case':case,'passed':bool(passed)}),flush=True)
    desktop=Desktop()
    with tempfile.TemporaryDirectory(prefix='luda-pm-range-') as temporary,patch.dict(os.environ,TMPDIR=temporary,GTK_IM_MODULE='gtk-im-context-simple'):
        worker=Worker(str(Path(temporary)/'profile'))
        try:
            root=f'http://127.0.0.1:{server.server_port}/index.html'
            opened=worker.open({'url':root,'executable':executable})
            end=time.monotonic()+3;windows=[]
            while not windows and time.monotonic()<end:windows=[w for w in desktop.list_windows() if w['pid']==opened['pid']];time.sleep(.02)
            if len(windows)!=1:raise RuntimeError('No exact native browser window')
            wid=windows[0]['window_id'];desktop.activate(wid)
            for name,seed,start,end,text,backward in CASES+[(name+'-delete-first',seed,start,end,text,backward) for name,seed,start,end,text,backward in CASES]+[(name+'-clipboard',seed,start,end,text,backward) for name,seed,start,end,text,backward in CASES]:
                worker.page.goto(root+'?seed='+seed);worker.page.wait_for_function('window.ludaSelectionProbe!==undefined')
                field=worker.inspect({'limit':10,'name':'Observed rich editor'})['fields'][0];token=field['token'];worker.focus(token)
                probe=SelectionProbe(worker,token,desktop,wid);before=probe.read();selected=None
                try:
                    selected=probe.select(start,end,backward)
                    result=probe.replace(text,delete_first=name.endswith('-delete-first'),clipboard=name.endswith('-clipboard'))
                    until=time.monotonic()+1
                    while oracle.get('model')!=result['model'] and time.monotonic()<until:worker.page.wait_for_timeout(10)
                    record(name,oracle.get('model')==result['model'] and oracle.get('modelText')==result['expected'],seed=seed,range=[start,end],inserted=text,before=before['model'],selection=selected,result=result,oracle=dict(oracle))
                except Refused as exc:
                    try:after=probe.read()
                    except Refused:after=None
                    record(name,False,error=exc.code,seed=seed,range=[start,end],inserted=text,before=before['model'],after=after,trace=getattr(probe,'trace',[]),selection=selected,oracle=dict(oracle))
            from luda.common import run
            clipboard_contents=run(['xclip','-selection','clipboard','-o']).decode()
            record('clipboard-route-explicit-side-effect',clipboard_contents=='new',clipboard_value=clipboard_contents,restored=False)

            for name,start,end in [('html-combining',8,9),('html-inside-zwj',2,4),('html-caret-combining',8,8)]:
                worker.page.goto(root+'?seed=plain');worker.page.wait_for_function('window.ludaSelectionProbe!==undefined')
                token=worker.inspect({'limit':10,'name':'HTML comparison'})['fields'][0]['token'];worker.focus(token)
                before=worker.snapshot(token,mutation=True,focus=True)[1];worker.select(token,start,end)
                try:
                    result=worker.type(token,'x','insert');after=worker.snapshot(token,mutation=True,focus=True)[1]
                    until=time.monotonic()+1
                    while oracle.get('htmlValue')!=after['text'] and time.monotonic()<until:worker.page.wait_for_timeout(10)
                    record(name,after['text']==before['text'][:start]+'x'+before['text'][end:] and oracle.get('htmlValue')==after['text'],actual=after,oracle=dict(oracle),result=result)
                except Refused as exc:record(name,False,error=exc.code,oracle=dict(oracle))

            def new_probe():
                worker.page.goto(root+'?seed=plain');worker.page.wait_for_function('window.ludaSelectionProbe!==undefined')
                token=worker.inspect({'limit':10,'name':'Observed rich editor'})['fields'][0]['token'];worker.focus(token)
                return SelectionProbe(worker,token,desktop,wid)
            def button(name):
                tree=desktop.inspect(wid,name=name);node=next(n for n in tree['nodes'] if n['name']==name and n['role']=='push button')
                desktop.element(node['element_id'],'invoke',action='press')
            probe=new_probe();held=probe.capture();button('Same-length update');worker.focus(probe.token)
            changed=probe.read()['model']
            try:probe.select(1,2,held=held);record('held-model-identity-race',False)
            except Refused as exc:record('held-model-identity-race',exc.code=='STALE_TARGET' and probe.read()['model']==changed,error=exc.code)
            finally:held.dispose()
            probe=new_probe();held=probe.capture();button('Renew registration')
            try:probe.select(1,2,held=held);record('registration-race',False)
            except Refused as exc:record('registration-race',exc.code=='STALE_TARGET',error=exc.code)
            finally:held.dispose()
            probe=new_probe();probe.select(1,5);button('Move focus after next input');worker.focus(probe.token);probe.select(1,5)
            try:probe.replace('first\nsecond');record('focus-after-first-action',False)
            except Refused as exc:
                until=time.monotonic()+1
                while 'first' not in oracle.get('modelText','') and time.monotonic()<until:worker.page.wait_for_timeout(10)
                record('focus-after-first-action',exc.code=='FOCUS_CHANGED' and 'first' in oracle.get('modelText','') and 'second' not in oracle.get('modelText',''),error=exc.code,oracle=dict(oracle))
        finally:
            if worker.context:worker.context.close()
            if worker.pw:worker.pw.stop()
            desktop.close();server.shutdown();server.server_close()
    return 0 if all(r['passed'] for r in rows) else 1

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--executable',required=True);raise SystemExit(main(p.parse_args().executable))
