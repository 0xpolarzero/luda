"""Test-only transparent stdio relay: one external move after an actual screenshot.

No response contents are changed. The original valid snapshot becomes stale
before it reaches the client, exactly as an independent window move can do.
"""
import json,os,subprocess,sys,threading,time
from pathlib import Path

def captured_window(message,requests,pid):
 if requests.get(message.get('id'))!='desktop_observe':return None
 result=message.get('result',{})
 if not any(c.get('type')=='image' for c in result.get('content',[])):return None
 for content in result.get('content',[]):
  if content.get('type')!='text':continue
  try:value=json.loads(content['text'])
  except (ValueError,KeyError):continue
  if value.get('ok') is not True:continue
  for window in value.get('windows',[]):
   if window.get('pid')==pid and window.get('title')=='Parcel Board':return window,value.get('snapshot_id')
 return None

def main():
 base=Path(sys.argv[1]);pid=int((base/'fixture.pid').read_text());requests={};moved=False
 process=subprocess.Popen([sys.argv[2]],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=sys.stderr)
 def forward():
  try:
   for line in sys.stdin.buffer:
    try:
     message=json.loads(line)
     if message.get('method')=='tools/call':requests[message.get('id')]=message.get('params',{}).get('name')
    except ValueError:pass
    process.stdin.write(line);process.stdin.flush()
  finally:process.stdin.close()
 threading.Thread(target=forward,daemon=True).start()
 try:
  for line in process.stdout:
   message=json.loads(line);window=captured_window(message,requests,pid) if not moved else None
   if window:
    w,snapshot=window;x=600 if w['frame_bounds']['x']<400 else 20
    subprocess.run(['wmctrl','-ir',str(w['xid']),'-e',f'0,{x},250,-1,-1'],check=True,timeout=3)
    deadline=time.monotonic()+3
    while True:
     raw=subprocess.check_output(['xwininfo','-id',str(w['xid'])],text=True,timeout=2)
     import re
     actual=int(re.search(r'Absolute upper-left X:\s*(-?\d+)',raw)[1])
     if abs(actual-w['bounds']['x'])>100:break
     if time.monotonic()>deadline:raise RuntimeError('Owned move did not change geometry')
     time.sleep(.02)
    (base/'moved.json').write_text(json.dumps({'moved':True,'snapshot_id':snapshot,'window_id':w['window_id'],'before_client_x':w['bounds']['x'],'after_client_x':actual,'requested_frame_x':x,'source':'External test orchestrator; no Luda response modified.'}))
    moved=True
   sys.stdout.buffer.write(line);sys.stdout.buffer.flush()
 finally:
  if process.poll() is None:
   process.terminate()
   try:process.wait(timeout=5)
   except subprocess.TimeoutExpired:process.kill();process.wait()
if __name__=='__main__':main()
