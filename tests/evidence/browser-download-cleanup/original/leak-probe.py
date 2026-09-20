import os,tempfile,pathlib,subprocess,json,time,http.server,threading
root=pathlib.Path(tempfile.mkdtemp(prefix='luda-browser-download-probe-'));runtime=root/'runtime';runtime.mkdir();tmp=root/'tmp';tmp.mkdir()
class H(http.server.BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_GET(self):
  self.send_response(200)
  if self.path=='/file':
   self.send_header('Content-Disposition','attachment; filename=synthetic.txt');body=b'owned synthetic download sentinel'
  else:
   self.send_header('Content-Type','text/html');body=b'<a download href="/file" id="d">download</a><script>setTimeout(()=>document.querySelector("a").click(),200)</script>'
  self.end_headers();self.wfile.write(body)
s=http.server.ThreadingHTTPServer(('127.0.0.1',0),H);threading.Thread(target=s.serve_forever,daemon=True).start()
r,w=os.pipe();p=subprocess.Popen(['/workspace/test-folder/luda/.venv/bin/python','-m','luda._browser_guard',str(runtime),str(w)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,env=dict(os.environ,TMPDIR=str(tmp)),pass_fds=(w,));os.close(w)
p.stdin.write((json.dumps({'op':'open','url':f'http://127.0.0.1:{s.server_port}','executable':'/workspace/silo-desktop-research/browsers/chromium-1243/chrome-linux-arm64/chrome'})+'\n').encode());p.stdin.flush();print(p.stdout.readline().decode().strip());time.sleep(2)
print('before',[(str(f.relative_to(root)),f.stat().st_size) for f in tmp.rglob('*') if f.is_file()]);p.stdin.close();p.wait(timeout=8);print('proof',os.read(r,1));print('after',[(str(f.relative_to(root)),f.stat().st_size) for f in root.rglob('*') if f.is_file()]);print('root',root);s.shutdown()
