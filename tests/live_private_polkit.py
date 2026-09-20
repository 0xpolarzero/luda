"""Cancel an actual private polkit/pkexec request through public native tools."""
import asyncio,base64,json,os,subprocess,sys,time
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
ROOT=Path(__file__).resolve().parents[1]
async def main(out):
 assert os.getuid()==1001 and os.environ.get('LUDA_TEST_AUTHORITY_PID')
 wm=subprocess.Popen(['xfwm4','--compositor=off'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);agent=None;responses=[]
 try:
  end=time.monotonic()+5
  while subprocess.run(['wmctrl','-m'],capture_output=True).returncode:
   assert time.monotonic()<end;await asyncio.sleep(.05)
  log=(out/'custom-agent.log').open('w');agent=subprocess.Popen(['/usr/bin/python3',str(ROOT/'tests/private_polkit_agent.py'),str(out)],stdout=log,stderr=log)
  def state():return json.loads((out/'state.json').read_text())
  end=time.monotonic()+8
  while not (out/'state.json').exists() or state()['begin_authentication']!=1:
   assert agent.poll() is None and time.monotonic()<end,'Authority did not request graphical authentication';await asyncio.sleep(.05)
  async with stdio_client(StdioServerParameters(command=str(ROOT/'.venv/bin/luda'),env=dict(os.environ))) as streams:
   async with ClientSession(*streams) as session:
    await session.initialize()
    async def call(name,**arguments):
     r=await session.call_tool(name,arguments);v=json.loads(r.content[0].text);responses.append({'tool':name,'arguments':arguments,'response':v});(out/'responses.json').write_text(json.dumps(responses,indent=2));assert not r.isError,(name,v)
     for c in r.content:
      if c.type=='image':(out/'dialog.png').write_bytes(base64.b64decode(c.data))
     return v
    windows=await call('desktop_windows');window=next(w for w in windows['windows'] if w['pid']==agent.pid);await call('desktop_activate',window_id=window['window_id']);await call('desktop_observe');tree=await call('desktop_inspect',window_id=window['window_id']);button=next(n for n in tree['nodes'] if n['name']=='Cancel' and n['role']=='push button');await call('desktop_invoke',element_id=button['element_id'])
    end=time.monotonic()+5
    while state()['caller_exit'] is None:
     assert time.monotonic()<end;await asyncio.sleep(.05)
    actual=state();assert actual['gui_cancel']==actual['begin_authentication']==1 and actual['caller_exit']==126 and actual['credentials_entered']==actual['authorization_responses']==0,actual
    assert not any(w['pid']==agent.pid for w in (await call('desktop_windows'))['windows'])
    (out/'result.json').write_text(json.dumps({'passed':True,'oracle':actual,'scope':'Real authority and pkexec; custom cancel-only agent, not GNOME dialog; no credentials or authorization'},indent=2))
 finally:
  (out/'stop').touch()
  if agent:
   try:agent.wait(timeout=3)
   except subprocess.TimeoutExpired:agent.kill();agent.wait()
  wm.terminate();wm.wait(timeout=3)
if __name__=='__main__':asyncio.run(main(Path(sys.argv[1])))
