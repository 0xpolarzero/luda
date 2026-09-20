"""MENU-08 native GTK tear-off workflow through actual public MCP tools."""
import asyncio
import base64
import json
import os
from pathlib import Path
import subprocess
import time
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts/detached-menu'
async def main():
 if os.getuid()==0 or os.environ.get('LUDA_ISOLATED_TEST_DISPLAY')!='1':raise RuntimeError('Private ordinary-user matrix session required')
 OUT.mkdir(parents=True,exist_ok=True);records=[]
 for name in ('state.json','proof.txt'):(OUT/name).unlink(missing_ok=True)
 def record(name,passed,**details):
  r=dict(case=name,passed=bool(passed),**details);records.append(r);print(json.dumps(r),flush=True)
 def state():return json.loads((OUT/'state.json').read_text())
 app=subprocess.Popen(['/usr/bin/python3',str(ROOT/'tests/detached_menu_fixture.py'),str(OUT)],stdout=subprocess.DEVNULL,stderr=(OUT/'fixture.log').open('w'))
 try:
  async with stdio_client(StdioServerParameters(command=str(ROOT/'.venv/bin/luda'),env=dict(os.environ))) as streams:
   async with ClientSession(*streams) as session:
    await session.initialize()
    async def raw(name,**args):
     r=await session.call_tool(name,args);return r.isError,json.loads(r.content[0].text)
    async def call(name,**args):
     error,value=await raw(name,**args)
     if error:raise RuntimeError(name+': '+json.dumps(value))
     return value
    async def wait(fn,timeout=5):
     deadline=time.monotonic()+timeout
     while time.monotonic()<deadline:
      result=await fn()
      if result:return result
      await asyncio.sleep(.05)
     raise RuntimeError('Bounded fixture readiness failed')
    async def find_window(title):
     windows=(await call('desktop_windows'))['windows']
     return next((w for w in windows if w['pid']==app.pid and w['title']==title),None)
    async def observe(label):
     r=await session.call_tool('desktop_observe',{})
     for content in r.content:
      if content.type=='image':(OUT/(label+'.png')).write_bytes(base64.b64decode(content.data))
     value=json.loads(r.content[0].text);(OUT/(label+'.json')).write_text(json.dumps(value,indent=2));return value
    owner=await wait(lambda:find_window('Luda Tear-off Owner'));wid=owner['window_id']
    await call('desktop_activate',window_id=wid)
    tree=await call('desktop_inspect',window_id=wid)
    button=next(n for n in tree['nodes'] if n['name']=='Open detachable actions' and n['role']=='push button')
    await call('desktop_invoke',element_id=button['element_id'],action='click')
    shot=await observe('attached-menu')
    popups=[p for p in shot['popups'] if p['owner_window_id']==wid]
    record('owned-attached-menu-observed',len(popups)==1 and not state()['detached'],popups=popups)
    if len(popups)!=1:raise RuntimeError('No unique owned popup')
    # The retained attached-menu screenshot shows the native dashed tear-off
    # row eight screenshot pixels below this fixture's observed menu top edge.
    menu=popups[0]['image_bounds'];x=menu['x']+menu['width']//2;y=menu['y']+8
    await call('desktop_click',window_id=wid,snapshot_id=shot['snapshot_id'],x=x,y=y)
    async def detached_state():return state()['detached']
    await wait(detached_state)
    detached=await wait(lambda:find_window('Luda Detached Actions'));did=detached['window_id']
    record('tear-off-creates-new-window-context',did!=wid and detached['xid']!=popups[0]['xid'] and state()['proof']==0 and state()['wrong']==0)
    err,old=await raw('desktop_click',window_id=wid,snapshot_id=shot['snapshot_id'],x=x,y=y)
    record('attached-popup-snapshot-refused-after-tearoff',err and old.get('code') in ('STALE_OBSERVATION','FOCUS_CHANGED') and state()['proof']==0 and state()['wrong']==0,code=old.get('code'))
    await call('desktop_activate',window_id=did)
    await call('desktop_window',window_id=did,action='move',x=700,y=180)
    fresh=await observe('detached-menu')
    current=next(w for w in fresh['windows'] if w['window_id']==did)
    err,detached_tree=await raw('desktop_inspect',window_id=did,limit=500)
    (OUT/'detached-tree.json').write_text(json.dumps(detached_tree,indent=2))
    record('detached-inspection-probe',not err,code=detached_tree.get('code'))
    if err:raise RuntimeError('Detached semantic provider unavailable')
    item=next(n for n in detached_tree['nodes'] if n['name']=='Write detached proof' and n['role']=='menu item')
    b=item['bounds'];image=fresh['image_size'];native=fresh['desktop_size']
    px=(b['x']+b['width']//2)*image['width']/native['width'];py=(b['y']+b['height']//2)*image['height']/native['height']
    await call('desktop_click',window_id=did,snapshot_id=fresh['snapshot_id'],x=px,y=py)
    async def proof_written():return state()['proof']==1 and (OUT/'proof.txt').exists()
    await wait(proof_written)
    record('moved-detached-coordinate-action-exact',state()['wrong']==0 and (OUT/'proof.txt').read_text()=='detached exact 日本語\n' and current['bounds']['x']>=690 and current['image_bounds'] is not None)
    await call('desktop_window',window_id=did,action='close')
    await call('desktop_wait',condition='window_absent',window_id=did,timeout=4)
    async def reattached():return not state()['detached']
    await wait(reattached)
    err,stale=await raw('desktop_invoke',element_id=item['element_id'],action='click')
    record('closed-detached-handle-refused',err and stale.get('code')=='STALE_TARGET' and state()['proof']==1 and state()['wrong']==0,code=stale.get('code'))
    await call('desktop_activate',window_id=wid)
    tree=await call('desktop_inspect',window_id=wid)
    button=next(n for n in tree['nodes'] if n['name']=='Open detachable actions' and n['role']=='push button')
    await call('desktop_invoke',element_id=button['element_id'],action='click')
    reopened=await observe('reattached-menu')
    record('owner-deliberately-reopens-attached-menu',not state()['detached'] and any(p['owner_window_id']==wid for p in reopened['popups']) and state()['proof']==1 and state()['wrong']==0)
    await call('desktop_press_keys',window_id=wid,chord='Escape')


 except Exception as exc:
  record('harness-failure',False,error=type(exc).__name__,message=str(exc))
 finally:
  if app.poll() is None:app.terminate();app.wait(timeout=3)
  (OUT/'results.json').write_text(json.dumps(dict(uid=os.getuid(),cases=records),indent=2)+'\n')
 return 0 if records and all(r['passed'] for r in records) else 1
if __name__=='__main__':raise SystemExit(asyncio.run(main()))
