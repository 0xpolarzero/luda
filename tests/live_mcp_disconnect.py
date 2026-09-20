"""Real MCP stdin EOF after independently observed input/action start, no cancellation."""
import asyncio
import json
import os
from pathlib import Path
import subprocess
import time
from live_keyboard_guard import Oracle,descendants
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts/mcp-disconnect'

class Client:
 def __init__(self,label,command=None):self.command=command;self.label=label;self.pending={};self.next_id=0;self.process=None;self.task=None;self.forced_shutdown=False
 async def start(self):
  self.log=(OUT/(self.label+'-stderr.log')).open('w')
  self.process=await asyncio.create_subprocess_exec(self.command or str(ROOT/'.venv/bin/luda'),stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=self.log,start_new_session=True)
  self.task=asyncio.create_task(self.read())
  await self.request('initialize',{'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'luda-eof-fixture','version':'1'}})
  await self.send({'jsonrpc':'2.0','method':'notifications/initialized'})
  return self
 async def send(self,value):self.process.stdin.write((json.dumps(value)+'\n').encode());await self.process.stdin.drain()
 async def begin(self,method,params):
  self.next_id+=1;future=asyncio.get_running_loop().create_future();self.pending[self.next_id]=future
  await self.send({'jsonrpc':'2.0','id':self.next_id,'method':method,'params':params});return future
 async def request(self,method,params):return await asyncio.wait_for(await self.begin(method,params),15)
 async def read(self):
  while line:=await self.process.stdout.readline():
   data=json.loads(line)
   if data.get('id') in self.pending:
    future=self.pending[data['id']]
    if not future.done():future.set_result(data)
 async def call(self,name,**arguments):
  result=(await self.request('tools/call',{'name':name,'arguments':arguments}))['result'];value=json.loads(result['content'][0]['text'])
  if result.get('isError'):raise RuntimeError(name+': '+value.get('code','error'))
  return value
 async def eof(self):
  self.process.stdin.close();await self.process.stdin.wait_closed()
 async def exited(self,timeout=16):
  code=await asyncio.wait_for(self.process.wait(),timeout);await asyncio.wait_for(self.task,2);return code
 async def close(self):
  if self.process and self.process.returncode is None:
   if not self.process.stdin.is_closing():await self.eof()
   try:await self.exited()
   except asyncio.TimeoutError:
    self.forced_shutdown=True;self.process.kill();await self.process.wait()
  if self.task and not self.task.done():self.task.cancel()
  self.log.close()

async def wait(predicate,timeout=5):
 end=time.monotonic()+timeout
 while time.monotonic()<end:
  value=predicate()
  if value:return value
  await asyncio.sleep(.001)
 raise RuntimeError('Independent mutation-phase/oracle timeout')

def process_identities(pid):
 result={};queue=descendants(pid)
 while queue:
  child=queue.pop();queue.extend(descendants(child))
  try:result[child]=Path('/proc',str(child),'stat').read_text().rsplit(')',1)[1].split()[19]
  except FileNotFoundError:pass
 return result

def alive(identities):
 result=[]
 for pid,start in identities.items():
  try:
   fields=Path('/proc',str(pid),'stat').read_text().rsplit(')',1)[1].split()
   if fields[19]==start and fields[0]!='Z':result.append(pid)
  except FileNotFoundError:pass
 return result

async def main():
 if os.getuid()==0 or os.environ.get('LUDA_ISOLATED_TEST_DISPLAY')!='1':raise RuntimeError('Private ordinary-user matrix session required')
 OUT.mkdir(parents=True,exist_ok=True);records=[];clients=[];fixture=None;oracle=None
 for name in ('started','release','state.json'):(OUT/name).unlink(missing_ok=True)
 def record(case,passed,**details):
  row=dict(case=case,passed=bool(passed),**details);records.append(row);print(json.dumps(row),flush=True)
 def state():return json.loads((OUT/'state.json').read_text())
 async def new(label):
  c=Client(label);clients.append(c);return await c.start()
 async def target(c):
  end=time.monotonic()+5
  while time.monotonic()<end:
   windows=(await c.call('desktop_windows'))['windows']
   found=next((w for w in windows if w['pid']==fixture.pid),None)
   if found:return found['window_id']
   await asyncio.sleep(.05)
  raise RuntimeError('Fixture window absent')
 try:
  fixture=subprocess.Popen(['/usr/bin/python3',str(ROOT/'tests/disconnect_fixture.py'),str(OUT)],stdout=subprocess.DEVNULL,stderr=(OUT/'fixture.log').open('w'))
  oracle=Oracle();c=await new('keys');await c.call('desktop_control',action='resume');wid=await target(c);await c.call('desktop_activate',window_id=wid)
  await wait(lambda:(OUT/'state.json').exists())
  pending=await c.begin('tools/call',{'name':'desktop_press_keys','arguments':{'window_id':wid,'chord':'a','count':20}})
  await wait(lambda:oracle.code('a') in oracle.pressed())
  helpers=process_identities(c.process.pid)
  began=time.monotonic();record('real-key-down-precedes-stdin-eof',not pending.done(),owned_helpers=len(helpers))
  await c.eof();code=await c.exited()
  await wait(lambda:not oracle.pressed() and not oracle.buttons());await asyncio.sleep(.15)
  text=state()['text']
  record('eof-key-operation-cleaned',code==0 and not alive(helpers) and not oracle.pressed() and not oracle.buttons(),exit_code=code,seconds=round(time.monotonic()-began,3),surviving_helpers=alive(helpers))
  record('late-key-effects-within-single-request',text==('a'*len(text)) and 1<=len(text)<=20,characters_after_eof=len(text),request_count=20,response_after_eof=pending.done())
  c2=await new('after-keys');status=await c2.call('desktop_status');await asyncio.sleep(.4)
  record('new-session-does-not-replay-key-request',state()['text']==text and status['operations']==[])
  wid2=await target(c2);await c2.call('desktop_activate',window_id=wid2);await c2.call('desktop_press_keys',window_id=wid2,chord='z')
  await wait(lambda:state()['text']==text+'z')
  record('new-session-explicit-key-only',True)
  await c2.eof();await c2.exited()
  action=await new('action');wid3=await target(action);await action.call('desktop_activate',window_id=wid3)
  tree=await action.call('desktop_inspect',window_id=wid3);button=next(n for n in tree['nodes'] if n['name']=='Run gated action')
  pending_action=await action.begin('tools/call',{'name':'desktop_invoke','arguments':{'element_id':button['element_id'],'action':'click'}})
  await wait(lambda:(OUT/'started').exists());helpers=process_identities(action.process.pid)
  record('application-callback-started-before-eof',state()['started']==1 and state()['completed']==0 and not pending_action.done())
  began=time.monotonic();await action.eof();await asyncio.sleep(.1);(OUT/'release').write_text('explicit fixture gate release after EOF')
  code=await action.exited();await wait(lambda:state()['completed']==1)
  record('delivered-action-finishes-once-after-eof',state()['started']==1 and state()['completed']==1,late_effect=True,undo_claimed=False)
  record('action-server-helpers-cleaned',code==0 and not alive(helpers),exit_code=code,seconds=round(time.monotonic()-began,3),surviving_helpers=alive(helpers))
  final=await new('after-action');status=await final.call('desktop_status');await asyncio.sleep(.4)
  record('new-session-does-not-replay-delivered-action',state()['started']==1 and state()['completed']==1 and status['operations']==[])
  fresh_wid=await target(final);fresh=await final.call('desktop_inspect',window_id=fresh_wid);button=next(n for n in fresh['nodes'] if n['name']=='Run gated action')
  await final.call('desktop_invoke',element_id=button['element_id'],action='click');await wait(lambda:state()['completed']==2)
  record('new-session-explicit-action-only',state()['started']==2 and state()['completed']==2)
 except Exception as exc:record('harness-failure',False,error=type(exc).__name__,message=str(exc))
 finally:
  (OUT/'release').write_text('cleanup release')
  for c in reversed(clients):
   await c.close()
   if c.forced_shutdown:record('forced-harness-server-cleanup',False,client=c.label)
  if oracle:oracle.close()
  if fixture and fixture.poll() is None:fixture.terminate();fixture.wait(timeout=3)
  (OUT/'results.json').write_text(json.dumps(dict(uid=os.getuid(),cases=records),indent=2)+'\n')
 return 0 if records and all(r['passed'] for r in records) else 1
if __name__=='__main__':raise SystemExit(asyncio.run(main()))
