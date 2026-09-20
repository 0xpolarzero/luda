"""Actual native and explicit-clipboard hard breaks, passive real ProseMirror model oracle."""
import argparse,asyncio,http.server,json,os,threading,time
from pathlib import Path
from html.parser import HTMLParser
from unittest.mock import patch
import live_mcp_disconnect as wire
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts/owned-hard-breaks';ASSETS=ROOT/'tests/fixtures/owned-rich-hard-breaks'
def units(model):
 result=[]
 for i,p in enumerate(model['content']):
  if i:result.append(('\n','paragraph',None))
  for n in p.get('content',[]):
   marks=n.get('marks',[])
   if n['type']=='hard_break':result.append(('\n','hard_break',marks))
   elif n['type']=='text':result.extend((c,'text',marks) for c in n['text'])
   else:raise AssertionError('Unsupported oracle node')
 return result
class DomShape(HTMLParser):
 def __init__(self,html):
  super().__init__();self.paragraphs=0;self.hard_breaks=0;self.feed(html)
 def handle_starttag(self,tag,attrs):
  if tag=='p':self.paragraphs+=1
  if tag=='br' and 'ProseMirror-trailingBreak' not in dict(attrs).get('class','').split():self.hard_breaks+=1
async def main(executable):
 if os.getuid()==0 or os.environ.get('LUDA_ISOLATED_TEST_DISPLAY')!='1':raise RuntimeError('Private ordinary-user GUI required')
 OUT.mkdir(parents=True,exist_ok=True);wire.OUT=OUT;state={};rows=[]
 def record(name,passed,**details):
  rows.append(dict(case=name,passed=bool(passed),**details));(OUT/'results.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
  if not passed:raise AssertionError(name)
 class Handler(http.server.BaseHTTPRequestHandler):
  def log_message(self,*unused):pass
  def do_GET(self):
   name=self.path.split('?')[0];p=ROOT/'integrations/prosemirror/luda-prosemirror.mjs' if name=='/bridge.mjs' else ASSETS/('index.html' if name=='/' else name.lstrip('/'))
   if p.parent not in (ASSETS,ROOT/'integrations/prosemirror') or not p.is_file():self.send_error(404);return
   self.send_response(200);self.send_header('Content-Type','text/javascript' if p.suffix in ('.mjs','.js') else 'text/html; charset=utf-8');self.end_headers();self.wfile.write(p.read_bytes())
  def do_POST(self):
   value=json.loads(self.rfile.read(int(self.headers['Content-Length'])));state.clear();state.update(value);(OUT/'oracle.json').write_text(json.dumps(value,ensure_ascii=False,indent=2));self.send_response(204);self.end_headers()
 service=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=service.serve_forever,daemon=True).start()
 async def wait(fn):
  end=time.monotonic()+2
  while time.monotonic()<end:
   if fn():return
   await asyncio.sleep(.02)
  raise AssertionError('Independent app oracle deadline')
 with patch.dict(os.environ,LUDA_CHROMIUM_EXECUTABLE=executable,GTK_IM_MODULE='gtk-im-context-simple'):
  client=await wire.Client('mcp').start()
  async def request(tool,**kwargs):
   r=(await client.request('tools/call',{'name':tool,'arguments':kwargs}))['result'];v=json.loads(r['content'][0]['text']);return r,v
  async def call(tool,**kwargs):
   r,v=await request(tool,**kwargs)
   if r.get('isError'):raise AssertionError((tool,v))
   return v
  async def deny(tool,code,**kwargs):
   r,v=await request(tool,**kwargs);record(code,r.get('isError') and v['code']==code,response=v);return v
  try:
   opened=await call('desktop_open_browser',url=f'http://127.0.0.1:{service.server_port}',lifetime='temporary_session');wid=opened['window_id'];await call('desktop_activate',window_id=wid);await wait(lambda:'model' in state)
   async def field():
    tree=await call('desktop_inspect',window_id=wid,name='Observed rich editor',role='entry');f=tree['text_fields'];assert len(f)==1;return f[0]
   async def button(label):
    tree=await call('desktop_inspect',window_id=wid,name=label);n=next(n for n in tree['nodes'] if n['name']==label and n['role']=='push button');assert 'press' in n['actions'];await call('desktop_invoke',element_id=n['element_id'],action='press')
   async def fresh(label='Fresh hard-break editor'):
    old=state['generation'];await button(label);await wait(lambda:state['generation']>old);f=await field();return f['element_id']
   for transport in ['native','clipboard']:
    for name,payload in [('unicode','A😀 é 日本語'),('spaces','  a\t b\u00a0c  '),('consecutive','a\n\nb'),('trailing','a\n\n'),('only-breaks','\n\n')]:
     eid=await fresh();r=await call('desktop_type',element_id=eid,text=payload,mode='replace',line_breaks='hard_break',transport=transport);await wait(lambda:state['modelText']==payload)
     actual=units(state['model']);expected=[(c,'hard_break' if c=='\n' else 'text') for c in payload]
     record(transport+'-'+name,[(c,k) for c,k,m in actual]==expected and len(state['model']['content'])==1 and state['model']==r['model'],result=r,oracle=dict(state))
     shape=DomShape(state['html']);record(transport+'-'+name+'-rendered-structure',shape.paragraphs==1 and shape.hard_breaks==payload.count('\n'),html=state['html'])
     read=await call('desktop_read_text',element_id=eid);record(transport+'-'+name+'-caret',read['caret_offset']==len(payload) and state['modelCaretCodePoints']==len(payload) and read['line_break_boundaries']==[{'offset':i,'kind':'hard_break'} for i,c in enumerate(payload) if c=='\n'])
     if '\n' in payload:
      await wait(lambda:any(e.get('type')=='keydown' and e.get('key')=='Enter' and e.get('shift') and e.get('trusted') for e in state['events']))
      record(transport+'-'+name+'-trusted-shift-enter',True,events=state['events'])
   eid=await fresh('Mixed marked document');before=json.loads(json.dumps(state['model']));read=await call('desktop_read_text',element_id=eid);record('mixed-structure-read',read['text']=='A😀\néZ\nTAIL' and read['line_break_boundaries']==[{'offset':2,'kind':'hard_break'},{'offset':6,'kind':'paragraph'}],read=read,oracle=dict(state))
   await call('desktop_focus_element',element_id=eid);await call('desktop_select',element_id=eid,start_offset=len(read['text']),end_offset=len(read['text']));r=await call('desktop_type',element_id=eid,text='\nEND',line_breaks='hard_break');await wait(lambda:state['model']==r['model']);record('native-append-preserves-mixed-prefix',units(r['model'])[:len(units(before))]==units(before),result=r,oracle=dict(state))
   for policy,start,end in [('hard_break',1,5),('paragraph',2,7),('hard_break',2,3),('hard_break',6,7),('hard_break',3,3)]:
    eid=await fresh('Mixed marked document');before=json.loads(json.dumps(state['model']));old=units(before);await call('desktop_focus_element',element_id=eid);await call('desktop_select',element_id=eid,start_offset=start,end_offset=end)
    r=await call('desktop_type',element_id=eid,text='X\n😀',transport='clipboard',line_breaks=policy);await wait(lambda:state['model']==r['model']);actual=units(state['model']);inserted=[('X','text'),('\n',policy),('😀','text')]
    record(f'clipboard-mixed-{policy}-{start}-{end}',actual[:start]==old[:start] and actual[start+3:]==old[end:] and [(c,k) for c,k,m in actual[start:start+3]]==inserted,result=r,oracle=dict(state))
   eid=await fresh('Mixed marked document');r=await call('desktop_type',element_id=eid,text='FULL\nREPLACE\n',mode='replace',line_breaks='hard_break');await wait(lambda:state['model']==r['model']);record('native-full-replace-mixed',len(state['model']['content'])==1 and state['modelText']=='FULL\nREPLACE\n',result=r,oracle=dict(state))
   eid=await fresh();before=json.loads(json.dumps(state['model']));v=await deny('desktop_type','LINE_BREAK_SEMANTICS_REQUIRED',element_id=eid,text='no\nimplicit');record('missing-policy-no-mutation',v['effect']=='none' and state['model']==before)
   eid=await fresh('Legacy editor');before=json.loads(json.dumps(state['model']));v=await deny('desktop_type','UNSUPPORTED_ACTION',element_id=eid,text='x\ny',line_breaks='hard_break');record('legacy-policy-no-mutation',v['effect']=='none' and state['model']==before)
   eid=await fresh('Legacy mixed document');before=json.loads(json.dumps(state['model']));v=await deny('desktop_type','TEXT_REPRESENTATION_UNSUPPORTED',element_id=eid,text='no replacement',mode='replace');record('legacy-mixed-no-mutation',v['effect']=='none' and state['model']==before)
   eid=await fresh('Mixed marked document');await button('Insert image model node');await wait(lambda:'image' in state['unsupported']);before=json.loads(json.dumps(state['model']));v=await deny('desktop_type','TEXT_REPRESENTATION_UNSUPPORTED',element_id=eid,text='no mixed replacement',mode='replace',line_breaks='hard_break');record('unsupported-mixed-no-mutation',v['effect']=='none' and state['model']==before)
   eid=await fresh('Wrong break binding');v=await deny('desktop_type','TEXT_MISMATCH',element_id=eid,text='A\nB',line_breaks='hard_break');await wait(lambda:state['modelText']=='A\n');record('wrong-binding-stops-no-replay',v['effect']=='uncertain' and len(state['model']['content'])==2 and state['modelText']=='A\n',oracle=dict(state))
   eid=await fresh();await button('Move focus after next input');v=await deny('desktop_type','FOCUS_CHANGED',element_id=eid,text='FIRST\nSECOND',line_breaks='hard_break');await wait(lambda:state['modelText']=='FIRST');record('focus-change-stops',v['effect']=='uncertain' and state['modelText']=='FIRST',oracle=dict(state))
   eid=await fresh();await call('desktop_focus_element',element_id=eid);await call('desktop_press_keys',window_id=wid,chord='ctrl+shift+u')
   for digit in ['3','0','6','b']:await call('desktop_press_keys',window_id=wid,chord=digit)
   await wait(lambda:any(e['type']=='compositionstart' and e['trusted'] for e in state['events']))
   pending=await call('desktop_read_text',element_id=eid);before=json.loads(json.dumps(state['model']));record('native-preedit-observed',pending['composition']['known'] and pending['composition']['active'],read=pending,oracle=dict(state))
   for transport in ['native','clipboard']:
    v=await deny('desktop_type','IME_COMPOSITION_ACTIVE',element_id=eid,text='NO\nINPUT',line_breaks='hard_break',transport=transport);after=await call('desktop_read_text',element_id=eid);record(transport+'-preedit-refusal-preserves',v['effect']=='none' and state['model']==before and after['composition']['active'] and after['text']==pending['text'],response=v,oracle=dict(state))
  finally:await client.close();service.shutdown();service.server_close()
 return 0
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--executable',required=True);raise SystemExit(asyncio.run(main(p.parse_args().executable)))
