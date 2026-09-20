"""Actual public MCP password entry with content-free app oracle and adverse handlers."""
import argparse,asyncio,hashlib,http.server,json,os,threading,time,subprocess
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts/owned-secret'
HTML='''<!doctype html><meta charset="utf-8"><title>Owned secret fixture</title>
<style>input,button{font:20px sans-serif;margin:12px}input{display:block}</style>
<form onsubmit="event.preventDefault();submits++;save()">
<input type="password" id="password" aria-label="Password" value="initial">
<input id="decoy" aria-label="Decoy" value="untouched"><button type="submit" id="submit">Submit</button></form>
<button id="limit" onclick="password.maxLength=1;save()">Limit one</button>
<button id="unlimit" onclick="password.removeAttribute('maxlength');save()">Remove limit</button>
<button id="normal" onclick="mode='normal';save()">Normal</button>
<button id="focus" onclick="mode='focus';save()">Steal focus</button>
<button id="replace" onclick="mode='replace';save()">Replace on select</button>
<button id="reveal" onclick="mode='reveal';save()">Reveal on input</button>
<button id="plain" onclick="password.type='text';save()">Make ordinary</button>
<button id="reload" onclick="location.reload()">Reload</button>
<script>
let mode='normal',submits=0,pastes=0,inputs=0,seq=0,composition=false,composition_events=0;
document.addEventListener('compositionstart',e=>{if(e.isTrusted){composition=true;composition_events++;save()}});
document.addEventListener('compositionend',e=>{if(e.isTrusted){composition=false;composition_events++;save()}});
const hash=async text=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(text)))).map(x=>x.toString(16).padStart(2,'0')).join('');
async function save(){const n=++seq,p=document.querySelector('#password'),value=p.value;
 const buttons=Object.fromEntries(Array.from(document.querySelectorAll('button')).map(n=>{const r=n.getBoundingClientRect();return[n.id,{x:r.x+r.width/2,y:r.y+r.height/2}]}));
 const data={sequence:n,document:DOCUMENT_ID,hash:await hash(value),decoy_hash:await hash(decoy.value),active:document.activeElement.id,type:p.type,max_length:p.maxLength,mode,submits,pastes,inputs,composition,composition_events,buttons};
 fetch('/oracle',{method:'POST',body:JSON.stringify(data)});}
function wire(){const p=document.querySelector('#password');
 p.addEventListener('paste',e=>{e.preventDefault();pastes++;save()});
 p.addEventListener('focus',()=>{if(mode==='focus')decoy.focus();save()});
 p.addEventListener('select',e=>{if(mode==='replace'){mode='normal';const copy=p.cloneNode(true);p.replaceWith(copy);wire();save()}});
 p.addEventListener('input',()=>{inputs++;if(mode==='reveal')p.type='text';save()});
}wire();setInterval(save,100);save();
</script>'''
async def main(executable):
 assert os.getuid()!=0 and os.environ.get('LUDA_ISOLATED_TEST_DISPLAY')=='1'
 OUT.mkdir(parents=True,exist_ok=True);state={};lock=threading.Lock();generation=0;cases=[];responses=[]
 class Handler(http.server.BaseHTTPRequestHandler):
  def log_message(self,*args):pass
  def do_GET(self):
   nonlocal generation
   with lock:generation+=1;g=generation
   self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.end_headers();self.wfile.write(HTML.replace('DOCUMENT_ID',str(g)).encode())
  def do_POST(self):
   value=json.loads(self.rfile.read(int(self.headers['Content-Length'])))
   with lock:
    if (value['document'],value['sequence'])>(state.get('document',0),state.get('sequence',0)):state.clear();state.update(value)
   self.send_response(204);self.end_headers()
 owners=[]
 for selection in ('clipboard','primary'):
  p=subprocess.Popen(['xclip','-quiet','-selection',selection],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);p.stdin.write(('fixture-'+selection).encode());p.stdin.close();owners.append(p)
 server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
 def record(name,okay,detail=None):
  cases.append({'case':name,'passed':bool(okay),'detail':detail});(OUT/'results.json').write_text(json.dumps(cases,indent=2)+'\n');assert okay,name
 async def oracle(predicate=lambda x:True):
  with lock:seq=(state.get('document',0),state.get('sequence',0))
  end=time.monotonic()+3
  while time.monotonic()<end:
   with lock:v=dict(state)
   if (v.get('document',0),v.get('sequence',0))>seq and predicate(v):return v
   await asyncio.sleep(.03)
  raise AssertionError('Fresh independent oracle did not arrive')
 digest=lambda text:hashlib.sha256(text.encode()).hexdigest()
 secret_marker='LUDA_SECRET_SENTINEL_7e41';secret=secret_marker+'-\t秘密-👩🏽‍💻'
 params=StdioServerParameters(command=str(ROOT/'.venv/bin/luda'),env=dict(os.environ,LUDA_CHROMIUM_EXECUTABLE=executable,GTK_IM_MODULE='gtk-im-context-simple'))
 try:
  async with stdio_client(params) as streams:
   async with ClientSession(*streams) as session:
    await session.initialize()
    async def call(tool,allow_error=False,**args):
     r=await session.call_tool(tool,args);v=json.loads(r.content[0].text);responses.append(v)
     assert secret_marker not in json.dumps(v,ensure_ascii=False),(tool,'response leaked secret')
     if not allow_error:assert not r.isError and (tool=='desktop_report' or v.get('ok') is True),(tool,v)
     return v
    opened=await call('desktop_open_browser',url=f'http://127.0.0.1:{server.server_port}',lifetime='temporary_session');wid=opened['window_id'];await call('desktop_activate',window_id=wid)
    async def field(name):
     tree=await call('desktop_inspect',window_id=wid,name=name);return next(n['element_id'] for n in tree['text_fields'] if n['name']==name)
    async def button(name):
     # Deliberate public Tab navigation; app oracle only observes focus and never
     # supplies input or hidden DOM mutations. The target is a visible button.
     for _ in range(20):
      current=await oracle()
      if current['active']==name:
       await call('desktop_press_keys',window_id=wid,chord='space');return
      await call('desktop_press_keys',window_id=wid,chord='Tab')
     raise AssertionError('Visible fixture button was not reached')
    eid=await field('Password')
    await oracle()
    decoy=await field('Decoy');await call('desktop_focus_element',element_id=decoy)
    for bad in ('line\nbreak','carriage\rreturn'):
     denied=await call('desktop_type_secret',True,element_id=eid,text=bad);actual=await oracle()
     record('line-break-refused-'+str(ord(bad[4] if bad.startswith('line') else bad[8])),denied['code']=='UNSUPPORTED_TEXT' and denied['effect']=='none' and actual['active']=='decoy' and actual['hash']==digest('initial'),denied)
    for tool in ('desktop_read_text','desktop_type'):
     args={'element_id':eid}
     if tool=='desktop_type':args['text']='ordinary-attempt'
     refused=await call(tool,True,**args)
     record('ordinary-'+tool+'-refused',refused.get('code')=='PROTECTED_FIELD' and refused['effect']=='none',refused)
    clip_before={selection:subprocess.check_output(['xclip','-selection',selection,'-out']) for selection in ('clipboard','primary')}
    typed=await call('desktop_type_secret',element_id=eid,text=secret)
    actual=await oracle(lambda s:s['hash']==digest(secret))
    record('explicit-native-secret-no-submit',typed['effect']=='dispatched' and actual['submits']==0 and actual['pastes']==0 and actual['decoy_hash']==digest('untouched'),{'response':typed,'oracle':actual})
    clip_after={selection:subprocess.check_output(['xclip','-selection',selection,'-out']) for selection in ('clipboard','primary')}
    record('secret-preserves-clipboard-primary',clip_before==clip_after,{'unchanged':{key:clip_before[key]==clip_after[key] for key in clip_before},'contains_secret':any(secret.encode() in value for value in clip_after.values()),'primary_is_initial_secret':clip_after['primary']==b'initial','primary_is_empty':clip_after['primary']==b'','primary_is_decoy':clip_after['primary']==b'untouched','primary_is_page_text':b'Normal' in clip_after['primary'],'primary_bytes':len(clip_after['primary'])})
    denied=await call('desktop_read_text',True,element_id=eid)
    record('entered-secret-still-refuses-ordinary-read',denied.get('code')=='PROTECTED_FIELD' and denied['effect']=='none',denied)
    # The field blocks real paste; explicit secret transport never uses it.
    await call('desktop_paste',window_id=wid,text='blocked-public-paste')
    actual=await oracle(lambda s:s['pastes']==1)
    record('password-paste-blocked',actual['hash']==digest(secret),actual)
    before_clear={selection:subprocess.check_output(['xclip','-selection',selection,'-out']) for selection in ('clipboard','primary')}
    cleared=await call('desktop_type_secret',element_id=eid,text='')
    actual=await oracle(lambda s:s['hash']==digest(''))
    record('explicit-empty-secret-clear',cleared['effect']=='dispatched' and actual['submits']==0,cleared)
    after_clear={selection:subprocess.check_output(['xclip','-selection',selection,'-out']) for selection in ('clipboard','primary')}
    record('empty-clear-preserves-both-clipboard-selections',before_clear==after_clear and all(secret.encode() not in value for value in after_clear.values()))
    await button('limit')
    denied=await call('desktop_type_secret',True,element_id=eid,text='😀');actual=await oracle()
    record('declared-utf16-maxlength-refuses-before-focus',denied.get('code')=='UNSUPPORTED_TEXT' and denied['effect']=='none' and actual['active']=='limit' and actual['hash']==digest(''),denied)
    await button('unlimit')
    await button('focus')
    denied=await call('desktop_type_secret',True,element_id=eid,text=secret)
    actual=await oracle()
    record('focus-theft-refuses-secret',denied['code']=='FOCUS_CHANGED' and actual['hash']==digest('') and actual['decoy_hash']==digest('untouched'),denied)
    await button('normal')
    await call('desktop_type_secret',element_id=eid,text='prior-synthetic')
    await oracle(lambda s:s['hash']==digest('prior-synthetic'))
    await button('replace')
    denied=await call('desktop_type_secret',True,element_id=eid,text=secret)
    actual=await oracle()
    record('replacement-on-selection-refuses-content',denied.get('code')=='STALE_TARGET' and actual['hash']==digest('prior-synthetic'),denied)
    await button('plain')
    eid=await field('Password')
    denied=await call('desktop_type_secret',True,element_id=eid,text=secret)
    record('ordinary-type-rejected-before-focus',denied['code']=='NOT_PROTECTED_FIELD' and denied['effect']=='none',denied)
    await button('reload')
    await oracle(lambda s:s['mode']=='normal' and s['type']=='password')
    denied=await call('desktop_type_secret',True,element_id=eid,text=secret)
    record('document-change-refuses-old-handle',denied['code']=='STALE_TARGET' and denied['effect']=='none',denied)
    eid=await field('Password')
    await button('reveal')
    denied=await call('desktop_type_secret',True,element_id=eid,text=secret)
    actual=await oracle(lambda s:s['type']=='text')
    record('app-reveal-after-input-is-uncertain',denied['code']=='NOT_PROTECTED_FIELD' and denied['effect']=='uncertain' and actual['hash']==digest(secret) and actual['submits']==0,{'response':denied,'limitation':'Application changed its own masking while handling native input; this cannot be prevented atomically.'})
    # Isolate active-preedit refusal last; EOF closes this owned fixture.
    # A key or a reload shortcut is not assumed to prove composition completion.
    await button('reload');await oracle(lambda s:s['mode']=='normal' and s['type']=='password')
    eid=await field('Password');decoy=await field('Decoy')
    await call('desktop_focus_element',element_id=decoy)
    await call('desktop_press_keys',window_id=wid,chord='ctrl+shift+u')
    for digit in ('3','0','6','b'):await call('desktop_press_keys',window_id=wid,chord=digit)
    preedit=await oracle(lambda s:s['composition'] and s['composition_events']>0)
    denied=await call('desktop_type_secret',True,element_id=eid,text=secret);after=await oracle()
    record('native-composition-refuses-before-focus',denied.get('code')=='IME_COMPOSITION_ACTIVE' and denied['effect']=='none' and after['active']=='decoy' and after['composition'] and after['decoy_hash']==preedit['decoy_hash'] and after['hash']==preedit['hash'],{'response':denied,'composition_events':after['composition_events']})
    for tool in ('desktop_status','desktop_report'):
     result=await call(tool);record(tool+'-no-secret',secret_marker not in json.dumps(result,ensure_ascii=False))
    # Closing MCP below owns browser/profile cleanup; there is no separate close tool.
 finally:
  server.shutdown();server.server_close();(OUT/'responses.json').write_text(json.dumps(responses,indent=2)+'\n')
  for process in owners:
   if process.poll() is None:process.terminate()
   process.wait(timeout=3)
 print(json.dumps({'cases':len(cases),'passed':sum(c['passed'] for c in cases)}))
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--executable',required=True);args=p.parse_args();asyncio.run(main(args.executable))
