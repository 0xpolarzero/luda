"""Actual MCP mutation guard with a private synthetic screensaver and GTK oracle."""
import asyncio,json,os,subprocess,sys,tempfile,time
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
ROOT=Path(__file__).resolve().parents[1]
async def main():
 with tempfile.TemporaryDirectory(prefix='luda-session-input-') as directory:
  base=Path(directory);flag=base/'active';flag.write_text('false');ready=base/'ready';calls=base/'calls'
  provider=subprocess.Popen(['/usr/bin/python3',str(ROOT/'tests/session_state_fixture.py'),str(flag),str(ready),str(calls)])
  app=subprocess.Popen(['/usr/bin/python3',str(ROOT/'tests/fixture.py'),directory]);cases=[]
  async def wait(fn):
   end=time.monotonic()+4
   while time.monotonic()<end:
    if fn():return
    await asyncio.sleep(.02)
   raise AssertionError('Independent session-state oracle timeout')
  try:
   await wait(ready.exists);await wait(lambda:(base/'state.json').exists())
   async with stdio_client(StdioServerParameters(command=sys.executable,args=['-m','luda.server'],env=dict(os.environ))) as streams:
    async with ClientSession(*streams) as client:
     await client.initialize()
     async def call(name,**args):
      response=await client.call_tool(name,args);value=json.loads(response.content[0].text)
      assert not response.isError,(name,value);return value
     owner=None
     for _ in range(100):
      owner=next((w for w in (await call('desktop_windows'))['windows'] if w['pid']==app.pid),None)
      if owner:break
      await asyncio.sleep(.02)
     assert owner;wid=owner['window_id'];await call('desktop_activate',window_id=wid)
     tree=await call('desktop_inspect',window_id=wid);entry=next(n for n in tree['nodes'] if n['name']=='Contract text');button=next(n for n in tree['nodes'] if n['name']=='Record action')
     flag.write_text('true')
     doctor=await call('desktop_doctor');assert not doctor['ready'] and doctor['session_state']['input_ready'] is False
     shot=await call('desktop_observe');assert shot['snapshot_id']
     for name,args in [('desktop_press_keys',{'window_id':wid,'chord':'Return'}),('desktop_type',{'element_id':entry['element_id'],'text':'must not arrive','mode':'replace'}),('desktop_paste',{'window_id':wid,'text':'must not enter clipboard'}),('desktop_invoke',{'element_id':button['element_id']}),('desktop_activate',{'window_id':wid})]:
      response=await client.call_tool(name,args);value=json.loads(response.content[0].text)
      assert response.isError and value['code']=='SESSION_BLOCKED' and value['effect']=='none',(name,value)
     await asyncio.sleep(.1);state=json.loads((base/'state.json').read_text());assert state['text']=='' and state['clicks']==0
     cases.append('active-hint-blocks-keys-text-paste-invoke-activation-without-app-effect')
     await call('desktop_status')
     assert (await call('desktop_read_text',element_id=entry['element_id']))['text']==''
     assert (await call('desktop_recover_input'))['pending_count']==0
     cases.append('observation-readback-status-and-owned-recovery-remain-available')
     flag.write_text('false');text='Explicit new action 日本語 👩🏽\u200d💻'
     await call('desktop_type',element_id=entry['element_id'],text=text,mode='replace')
     await call('desktop_invoke',element_id=button['element_id'])
     await wait(lambda:json.loads((base/'state.json').read_text())['text']==text and json.loads((base/'state.json').read_text())['clicks']==1)
     assert set(calls.read_text().splitlines())=={'GetActive'}
     cases.append('inactive-hint-allows-explicit-new-actions-without-replaying-blocked-ones-or-unlocking')
  finally:
   for process in (app,provider):
    if process.poll() is None:process.terminate();process.wait(timeout=3)
 out=ROOT/'artifacts/session-input';out.mkdir(parents=True,exist_ok=True);value={'uid':os.getuid(),'passed':cases};(out/'results.json').write_text(json.dumps(value,indent=2)+'\n');print(json.dumps(value))
if __name__=='__main__':asyncio.run(main())
