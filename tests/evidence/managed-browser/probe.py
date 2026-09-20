"""Actual installed wheel -> managed session launcher -> MCP -> browser oracle."""
import argparse,asyncio,http.server,json,os,pwd,subprocess,sys,threading,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'tests'))
import live_mcp_disconnect as wire
parser=argparse.ArgumentParser();parser.add_argument('--prefix',type=Path,required=True);parser.add_argument('--output',type=Path,required=True);parser.add_argument('--replace-owned-executable',type=Path);args=parser.parse_args()
if os.getuid()==0 or os.environ.get('LUDA_ISOLATED_TEST_DISPLAY')!='1':raise SystemExit('Private ordinary-account session required')
args.output.mkdir(parents=True,exist_ok=True);wire.OUT=args.output
oracle={'text':None}
class Handler(http.server.BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_GET(self):
  self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.end_headers();self.wfile.write(b'<label>Managed field<textarea aria-label="Managed field" oninput="fetch(\'/state\',{method:\'POST\',body:this.value})"></textarea></label>')
 def do_POST(self):
  oracle['text']=self.rfile.read(int(self.headers['Content-Length'])).decode();self.send_response(204);self.end_headers()
async def main():
 server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
 log=(args.output/'xfce.log').open('w');xfce=subprocess.Popen(['xfce4-session','--disable-tcp'],stdout=log,stderr=log)
 client=wire.Client('managed');owned={};profile=None
 try:
  for _ in range(150):
   if subprocess.run(['wmctrl','-m'],capture_output=True).returncode==0:break
   await asyncio.sleep(.04)
  release=args.prefix/'current/.venv/bin'
  client.log=(args.output/'mcp.log').open('w')
  # Poison ambient selection: only the verified release configuration may win.
  env=dict(os.environ,LUDA_CHROMIUM_EXECUTABLE='/not-the-selected-browser')
  for variable in ('PYTHONPATH','PYTHONHOME'):env.pop(variable,None)
  client.process=await asyncio.create_subprocess_exec(str(release/'luda-session'),'--user',pwd.getpwuid(os.getuid()).pw_name,'--session-pid',str(xfce.pid),'--',str(release/'luda'),limit=2*1024*1024,env=env,stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=client.log,start_new_session=True)
  client.task=asyncio.create_task(client.read())
  await client.request('initialize',{'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'managed-browser-probe','version':'1'}});await client.send({'jsonrpc':'2.0','method':'notifications/initialized'})
  doctor=await client.call('desktop_doctor');cap=doctor['owned_browser']
  assert cap['available'] and cap['managed_selection_verified'] and cap['verified_executable_version']=='153.0.8010.12' and cap['playwright_version']=='1.63.0' and not cap['launch_verified'],cap
  replacement_refused=None
  if args.replace_owned_executable:
   executable=args.replace_owned_executable.resolve()
   selection=json.loads((args.prefix/'current/.venv/luda-browser.json').read_text())
   assert str(executable)==selection['executable'] and executable.stat().st_uid==os.getuid()
   backup=executable.with_name(executable.name+'.probe-original');assert not backup.exists()
   marker=args.output/'replacement-executed'
   executable.rename(backup)
   try:
    executable.write_text('#!/bin/sh\ntouch "'+str(marker)+'"\n');executable.chmod(0o755)
    response=await client.request('tools/call',{'name':'desktop_open_browser','arguments':{'url':'about:blank','lifetime':'temporary_session'}})
    value=json.loads(response['result']['content'][0]['text'])
    assert value['code']=='BROWSER_SELECTION_CHANGED' and value['effect']=='none',value
    assert not marker.exists();replacement_refused=True
   finally:
    executable.unlink(missing_ok=True);backup.rename(executable)
  opened=await client.call('desktop_open_browser',url=f'http://127.0.0.1:{server.server_port}',lifetime='temporary_session');wid=opened['window_id']
  await client.call('desktop_activate',window_id=wid)
  tree=await client.call('desktop_inspect',window_id=wid);field=next(n for n in tree['text_fields'] if n['name']=='Managed field')
  payload='managed 日本語 😀\nsecond line\n'
  typed=await client.call('desktop_type',element_id=field['element_id'],text=payload,mode='replace')
  for _ in range(100):
   if oracle['text']==payload:break
   await asyncio.sleep(.03)
  assert oracle['text']==payload,(typed,oracle)
  owned=wire.process_identities(client.process.pid)
  for pid in owned:
   try:parts=Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
   except FileNotFoundError:continue
   if b'luda._browser_worker' in parts:profile=Path(parts[-2].decode())
  assert profile and profile.exists()
  await client.eof();await client.exited()
  for _ in range(150):
   if not profile.exists() and not wire.alive(owned):break
   await asyncio.sleep(.03)
  assert not profile.exists() and not wire.alive(owned)
  result={'passed':True,'uid':os.getuid(),'release':(args.prefix/'current').resolve().name,'capability':cap,'actual_browser':opened,'independent_unicode_text_match':True,'cleanup_confirmed':True,'ambient_selection_ignored':True,'post_startup_replacement_refused':replacement_refused}
  (args.output/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
 finally:
  if client.process:await client.close()
  for pid in wire.alive(owned):
   try:os.kill(pid,9)
   except ProcessLookupError:pass
  xfce.terminate();xfce.wait(timeout=3);log.close();server.shutdown();server.server_close()
asyncio.run(main())
