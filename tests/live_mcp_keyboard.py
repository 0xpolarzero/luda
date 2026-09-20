"""Actual MCP bounded key repetition with private GTK text/navigation oracle."""
import asyncio,json,os,subprocess,sys,tempfile,time
from pathlib import Path
from mcp import ClientSession,StdioServerParameters,types
from mcp.client.stdio import stdio_client
from mcp.shared.exceptions import McpError
ROOT=Path(__file__).resolve().parents[1]


async def child():
 with tempfile.TemporaryDirectory(prefix='luda-mcp-keyboard-') as directory:
  out=Path(directory);wm=subprocess.Popen(['xfwm4','--compositor=off'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);fixture=None
  try:
   end=time.monotonic()+5
   while subprocess.run(['wmctrl','-m'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:
    assert time.monotonic()<end;await asyncio.sleep(.05)
   fixture=subprocess.Popen(['/usr/bin/python3',str(ROOT/'tests/keyboard_fixture.py'),directory],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
   async def oracle(predicate):
    end=time.monotonic()+3
    while time.monotonic()<end:
     try:
      value=json.loads((out/'state.json').read_text())['text']
      if predicate(value):return value
     except (FileNotFoundError,json.JSONDecodeError):pass
     await asyncio.sleep(.01)
    raise AssertionError('GTK text oracle did not reach expected state')
   async with stdio_client(StdioServerParameters(command=sys.executable,args=['-m','luda.server'],env=dict(os.environ))) as streams:
    async with ClientSession(*streams) as session:
     await session.initialize()
     schema=next(tool.inputSchema for tool in (await session.list_tools()).tools if tool.name=='desktop_press_keys')
     assert schema['properties']['count']['type']=='integer' and schema['properties']['count']['default']==1
     async def call(name,error=None,**args):
      response=await session.call_tool(name,args);value=json.loads(response.content[0].text)
      if error:assert response.isError and value['code']==error and value['effect']=='none',(name,value)
      else:assert not response.isError,(name,value)
      return value
     owner=None
     for _ in range(60):
      owner=next((w for w in (await call('desktop_windows'))['windows'] if w['pid']==fixture.pid),None)
      if owner:break
      await asyncio.sleep(.05)
     assert owner;wid=owner['window_id'];await call('desktop_activate',window_id=wid)
     for count in (True,'2',0,21,-1):await call('desktop_press_keys',error='INVALID_ARGUMENT',window_id=wid,chord='1',count=count)
     await oracle(lambda text:text=='')
     result=await call('desktop_press_keys',window_id=wid,chord='1',count=20)
     assert result['dispatched_count']==20;await oracle(lambda text:text=='1'*20)
     async def clear():
      await call('desktop_press_keys',window_id=wid,chord='ctrl+a')
      await call('desktop_press_keys',window_id=wid,chord='BackSpace')
     await clear();await call('desktop_press_keys',window_id=wid,chord='Return',count=3)
     await call('desktop_press_keys',window_id=wid,chord='Up',count=2)
     await call('desktop_press_keys',window_id=wid,chord='A');await oracle(lambda text:text=='\nA\n\n')
     await clear()
     request_id=session._request_id
     pending=asyncio.create_task(session.call_tool('desktop_press_keys',dict(window_id=wid,chord='1',count=20)))
     await oracle(lambda text:len(text)>=3)
     await session.send_notification(types.ClientNotification(types.CancelledNotification(params=types.CancelledNotificationParams(requestId=request_id,reason='owned repeat cancellation qualification'))))
     try:response=await asyncio.wait_for(pending,3);assert response.isError
     except McpError as exc:assert 'cancel' in str(exc).lower()
     deadline=time.monotonic()+4
     while True:
      status=await call('desktop_status')
      if not status.get('recovering') and any(row.get('code')=='CANCELLED' for row in status['operations']):break
      assert time.monotonic()<deadline;await asyncio.sleep(.03)
     value=await oracle(lambda text:3<=len(text)<20);await asyncio.sleep(.15)
     assert json.loads((out/'state.json').read_text())['text']==value
     await call('desktop_press_keys',window_id=wid,chord='A')
     await oracle(lambda text:text==value+'A')
     print(json.dumps({'suite':'mcp-keyboard-repeat','schema_integer_default':True,'invalid_counts_no_effect':True,'exact_repeat_count':20,'navigation_readback':True,'cancelled_repeat_no_replay':True,'same_mcp_session_usable':True}))
  finally:
   if fixture and fixture.poll() is None:fixture.terminate();fixture.wait(timeout=3)
   if wm.poll() is None:wm.terminate();wm.wait(timeout=3)


def main():
 if '--child' in sys.argv:return asyncio.run(child())
 with tempfile.TemporaryDirectory(prefix='luda-private-mcp-keys-') as directory:
  env=dict(os.environ)
  for key in ('XDG_CONFIG_HOME','XDG_DATA_HOME','XDG_CACHE_HOME','XDG_RUNTIME_DIR'):
   path=Path(directory)/key;path.mkdir(mode=0o700);env[key]=str(path)
  env['XDG_CONFIG_DIRS']=env['XDG_CONFIG_HOME']
  result=subprocess.run(['xvfb-run','-a','dbus-run-session','--',sys.executable,__file__,'--child'],env=env,timeout=30)
 raise SystemExit(result.returncode)

if __name__=='__main__':main()
