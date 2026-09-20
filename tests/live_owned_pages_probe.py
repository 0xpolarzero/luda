"""Public native inspection remains usable while owned page fields are out of scope."""
import argparse,asyncio,base64,http.server,json,os,subprocess,threading,time
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts/owned-pages-probe'
async def main(executable):
 assert os.getuid()!=0 and os.environ.get('LUDA_ISOLATED_TEST_DISPLAY')=='1'
 OUT.mkdir(parents=True,exist_ok=True);state={};responses=[];records=[];ports={}
 class Handler(http.server.BaseHTTPRequestHandler):
  def log_message(self,*args):pass
  def do_GET(self):
   if self.path.startswith('/child'):
    html='''<h1>Local child</h1><label>Child note<input aria-label="Child note" id="note" autofocus></label><button onclick="completed++;save();window.opener?.postMessage('done','MAIN')">Complete</button>'''.replace('MAIN',f'http://127.0.0.1:{ports["main"]}')
    tag='child'
   else:
    html='''<h1>Local opener</h1><label>Opener note<input aria-label="Opener note" id="note"></label><button onclick="window.open('CHILD','_blank')">Open tab</button><button onclick="window.open('CHILD','popup','popup,width=650,height=550')">Open popup</button><p id="receipt">Pending</p>'''.replace('CHILD',f'http://127.0.0.1:{ports["child"]}/child');tag='main'
   script="""<script>let completed=0,inputs=0;function save(){fetch('/oracle',{method:'POST',body:JSON.stringify({tag:'TAG',origin:location.origin,note:note.value,inputs,completed})})}note.addEventListener('input',()=>{inputs++;save()});window.addEventListener('message',e=>{if(e.origin==='CHILD'&&e.data==='done'){completed++;receipt.textContent='Returned from child';save()}});setInterval(save,100);save();</script>""".replace('TAG',tag).replace('CHILD',f'http://127.0.0.1:{ports["child"]}')
   body='<meta charset="utf-8"><title>Same Title</title><style>body{font:22px sans-serif;padding:30px}input,button{font:22px sans-serif;display:block;margin:15px}</style>'+html+script
   self.send_response(200);self.send_header('Content-Type','text/html;charset=utf-8');self.end_headers();self.wfile.write(body.encode())
  def do_POST(self):
   value=json.loads(self.rfile.read(int(self.headers['Content-Length'])));state[value['tag']]=value;self.send_response(204);self.end_headers()
 servers=[]
 for key in ('main','child'):
  server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler);ports[key]=server.server_port;servers.append(server);threading.Thread(target=server.serve_forever,daemon=True).start()
 def record(name,**detail):records.append({'case':name,**detail});(OUT/'results.json').write_text(json.dumps(records,indent=2))
 async def until(predicate):
  end=time.monotonic()+4
  while time.monotonic()<end:
   if predicate():return
   await asyncio.sleep(.05)
  raise AssertionError('Independent page oracle timeout')
 params=StdioServerParameters(command=str(ROOT/'.venv/bin/luda'),env=dict(os.environ,LUDA_CHROMIUM_EXECUTABLE=executable))
 try:
  async with stdio_client(params) as streams:
   async with ClientSession(*streams) as session:
    await session.initialize()
    async def call(tool,allow_error=False,**args):
     raw=await session.call_tool(tool,args);v=json.loads(raw.content[0].text);responses.append({'tool':tool,'arguments':args,'response':v});(OUT/'responses.json').write_text(json.dumps(responses,indent=2))
     for c in raw.content:
      if c.type=='image':(OUT/(str(len(responses))+'-observe.png')).write_bytes(base64.b64decode(c.data))
     if not allow_error:assert not raw.isError,(tool,v)
     return v
    opened=await call('desktop_open_browser',url=f'http://127.0.0.1:{ports["main"]}/',lifetime='temporary_session');wid=opened['window_id'];await call('desktop_activate',window_id=wid)
    async def click(name,target=wid):
     tree=await call('desktop_inspect',window_id=target,name=name);node=next(n for n in tree['nodes'] if n['name']==name and n['role']=='push button');await call('desktop_invoke',element_id=node['element_id'],action=next(a for a in node['actions'] if a=='press'))
    initial=await call('desktop_inspect',window_id=wid,role='entry');field=next(n['element_id'] for n in initial['text_fields'] if n['name']=='Opener note')
    await click('Open tab');await until(lambda:'child' in state)
    tabs=await call('desktop_inspect',True,window_id=wid,role='entry');record('two-tabs-inspection',response=tabs,oracle=dict(state));assert tabs.get('ok') and tabs['nodes'] and tabs['text_fields']==[] and tabs['owned_browser']=={'available':False,'code':'BROWSER_SCOPE_UNSUPPORTED'}
    old=await call('desktop_read_text',True,element_id=field);record('two-tabs-old-owned-field',response=old);assert old.get('code')=='BROWSER_SCOPE_UNSUPPORTED' and old['effect']=='none'
    await call('desktop_observe');await call('desktop_press_keys',window_id=wid,chord='ctrl+w');await asyncio.sleep(.3)
    restored=await call('desktop_inspect',window_id=wid,role='entry');record('one-page-restores-owned-fields',fields=[n['name'] for n in restored['text_fields']]);assert any(n['name']=='Opener note' for n in restored['text_fields'])
    await click('Open popup');await asyncio.sleep(.3);windows=await call('desktop_windows');popup=next(w for w in windows['windows'] if w['window_id']!=wid and w['title'].startswith('Same Title'))['window_id']
    opener=await call('desktop_inspect',True,window_id=wid,role='entry');record('popup-opener-retains-native-inspection',response=opener);assert opener.get('ok') and opener['nodes'] and opener['text_fields']==[] and opener['owned_browser']['code']=='BROWSER_SCOPE_UNSUPPORTED'
    await call('desktop_activate',window_id=popup);native=await call('desktop_inspect',window_id=popup);record('popup-native-inspection',nodes=[{'name':n['name'],'role':n['role']} for n in native['nodes']],has_owned_fields='text_fields' in native)
    await call('desktop_press_keys',window_id=popup,chord='ctrl+l');address=await call('desktop_inspect',window_id=popup,name='Address and search bar');entries=[n for n in address['nodes'] if n['name']=='Address and search bar']
    if entries:
     read=await call('desktop_read_text',True,element_id=entries[0]['element_id']);record('popup-address-read',response=read,expected_origin=f'http://127.0.0.1:{ports["child"]}')
    await call('desktop_observe');await call('desktop_press_keys',window_id=popup,chord='Escape')
    await click('Complete',popup);await until(lambda:state.get('main',{}).get('completed')==1);record('explicit-native-complete-return',oracle=dict(state));assert state['main']['completed']==state['child']['completed']==1 and state['main']['inputs']==state['child']['inputs']==0
    await call('desktop_press_keys',window_id=popup,chord='ctrl+w');await call('desktop_activate',window_id=wid);final=await call('desktop_inspect',window_id=wid,name='Returned from child');record('opener-resumed',receipt=any(n['name']=='Returned from child' for n in final['nodes']));assert any(n['name']=='Returned from child' for n in final['nodes'])
 finally:
  for server in servers:server.shutdown();server.server_close()
 return 0
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--executable',required=True);raise SystemExit(asyncio.run(main(p.parse_args().executable)))
