import asyncio,http.server,threading,tempfile,json,os,signal,subprocess,sys,time,hashlib
from pathlib import Path
sys.path.insert(0,'/workspace/test-folder/luda/tests')
import live_mcp_disconnect as wire
ROOT=Path(tempfile.mkdtemp(prefix='download-review-',dir='/workspace/luda-browser-review-real'));wire.OUT=ROOT
external=ROOT/'long-caller-temporary-directory';external.mkdir();os.environ['TMPDIR']=str(external)
class H(http.server.BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_GET(self):
  self.send_response(200)
  if self.path=='/file':self.send_header('Content-Disposition','attachment; filename=synthetic.txt');body=b'owned synthetic download sentinel'
  else:self.send_header('Content-Type','text/html');body=b'<a download href="/file">download</a><script>setTimeout(()=>document.querySelector("a").click(),200)</script>'
  self.end_headers();self.wfile.write(body)
server=http.server.ThreadingHTTPServer(('127.0.0.1',0),H);threading.Thread(target=server.serve_forever,daemon=True).start()
async def main():
 records=[];wm=subprocess.Popen(['xfwm4','--compositor=off'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 try:
  for _ in range(100):
   if subprocess.run(['wmctrl','-m'],capture_output=True).returncode==0:break
   await asyncio.sleep(.03)
  for mode in ('eof','worker-killed','server-killed'):
   client=await wire.Client(mode).start();owned={}
   try:
    await client.call('desktop_open_browser',url=f'http://127.0.0.1:{server.server_port}',lifetime='temporary_session')
    owned=wire.process_identities(client.process.pid);profile=None;worker=None
    for pid in owned:
     try:args=Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
     except FileNotFoundError:continue
     if b'luda._browser_worker' in args:worker=pid;profile=Path(args[-2].decode())
    assert worker and profile and profile.exists()
    deadline=time.monotonic()+4;attachments=[]
    while not attachments and time.monotonic()<deadline:
     attachments=[p for p in profile.rglob('*') if p.is_file() and not p.is_symlink() and p.stat().st_size==33 and p.read_bytes()==b'owned synthetic download sentinel']
     if not attachments:await asyncio.sleep(.03)
    assert attachments,'No actual attachment before fault'
    assert not any(p.is_file() and p.stat().st_size==33 for p in external.rglob('*'))
    if mode=='eof':await client.eof()
    elif mode=='worker-killed':os.kill(worker,signal.SIGKILL)
    else:client.process.kill()
    deadline=time.monotonic()+8
    while (profile.exists() or wire.alive(owned)) and time.monotonic()<deadline:await asyncio.sleep(.03)
    assert not profile.exists() and not wire.alive(owned),(mode,str(profile),wire.alive(owned))
    assert not any(p.is_file() and p.stat().st_size==33 for p in external.rglob('*'))
    records.append({'mode':mode,'actual_attachment_bytes':33,'owned_processes':len(owned),'profile_removed':True,'survivors':[],'external_attachment_files':0})
   finally:await client.close()
 finally:wm.terminate();wm.wait(timeout=3);server.shutdown();server.server_close()
 files=['browser.py','_browser_guard.py','_browser_worker.py']; hashes={name:hashlib.sha256((Path('/workspace/test-folder/luda/src/luda')/name).read_bytes()).hexdigest() for name in files}
 value={'uid':os.getuid(),'records':records,'source_hashes':hashes,'root':str(ROOT)};(ROOT/'result.json').write_text(json.dumps(value,indent=2));print(json.dumps(value))
asyncio.run(main())
