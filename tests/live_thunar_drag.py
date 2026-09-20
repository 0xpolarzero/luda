"""PTR-09 real Thunar right-drag intent menu, actual MCP and file oracles."""
import asyncio
import base64
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'artifacts/thunar-drag'
async def main():
 if os.getuid()==0 or os.environ.get('LUDA_ISOLATED_TEST_DISPLAY')!='1': raise RuntimeError('Private ordinary-user matrix required')
 OUT.mkdir(parents=True,exist_ok=True); records=[]; processes=[]
 # The matrix archives each preceding run before another invocation.
 for old in OUT.iterdir():
  if old.is_file():old.unlink()
 def record(case,passed,**details):
  row=dict(case=case,passed=bool(passed),**details); records.append(row); print(json.dumps(row),flush=True)
 try:
  with tempfile.TemporaryDirectory(prefix='luda-thunar-drag-') as directory:
   root=Path(directory); payload=b'owned binary\x00\xff\n'+ '日本語 👩🏽‍💻'.encode()
   async with stdio_client(StdioServerParameters(command=str(ROOT/'.venv/bin/luda'),env=dict(os.environ))) as streams:
    async with ClientSession(*streams) as session:
     await session.initialize()
     async def call(name,**args):
      result=await session.call_tool(name,args); value=json.loads(result.content[0].text)
      if result.isError: raise RuntimeError(name+': '+json.dumps(value))
      return value
     async def wait(fn,timeout=5):
      deadline=time.monotonic()+timeout
      while time.monotonic()<deadline:
       value=await fn()
       if value:return value
       await asyncio.sleep(.08)
      raise RuntimeError('Bounded readiness failed')
     async def window(title):
      windows=(await call('desktop_windows'))['windows']; (OUT/'windows.json').write_text(json.dumps(windows,indent=2))
      return next((w for w in windows if w['title']==title or w['title'].startswith(title+' - ')),None)
     async def observe(label):
      r=await session.call_tool('desktop_observe',{})
      if r.isError:raise RuntimeError(r.content[0].text)
      for item in r.content:
       if item.type=='image':(OUT/(label+'.png')).write_bytes(base64.b64decode(item.data))
      shot=json.loads(r.content[0].text); (OUT/(label+'.json')).write_text(json.dumps(shot,indent=2));return shot
     for mode,row in [('copy',0),('move',1),('link',2),('cancel',3),('conflict-cancel',0)]:
      source=root/(mode+'-source'); target=root/(mode+'-target');source.mkdir();target.mkdir()
      original=source/'proof.bin'; original.write_bytes(payload); source_inode=original.stat().st_ino
      destination=target/original.name
      conflict=b'preserve existing destination\x00\xfe'
      if mode=='conflict-cancel':destination.write_bytes(conflict)
      target_inode=destination.stat().st_ino if destination.exists() else None
      processes.append(subprocess.Popen(['thunar',str(source)],stdout=subprocess.DEVNULL,stderr=(OUT/(mode+'-thunar.log')).open('w')))
      src=await wait(lambda:window(source.name));sid=src['window_id']
      processes.append(subprocess.Popen(['thunar',str(target)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL))
      dst=await wait(lambda:window(target.name));tid=dst['window_id']
      for wid,x in ((sid,20),(tid,730)):
       await call('desktop_window',window_id=wid,action='resize',width=650,height=620)
       await call('desktop_window',window_id=wid,action='move',x=x,y=100)
      await call('desktop_activate',window_id=sid)
      await call('desktop_press_keys',window_id=sid,chord='ctrl+2')
      async def file_node():
       tree=await call('desktop_inspect',window_id=sid,limit=500)
       (OUT/(mode+'-source-tree.json')).write_text(json.dumps(tree,indent=2))
       return next((n for n in tree['nodes'] if n['name']=='proof.bin' and n.get('bounds') and 'showing' in n['states']),None)
      file=await wait(file_node)
      shot=await observe(mode+'-before-drag');b=file['bounds'];dest=next(w for w in shot['windows'] if w['window_id']==tid)['bounds']
      sx=shot['image_size']['width']/shot['desktop_size']['width'];sy=shot['image_size']['height']/shot['desktop_size']['height']
      response=await call('desktop_drag_to',source_window_id=sid,target_window_id=tid,snapshot_id=shot['snapshot_id'],x=(b['x']+b['width']/2)*sx,y=(b['y']+b['height']/2)*sy,end_x=(dest['x']+450)*sx,end_y=(dest['y']+400)*sy,button='right')
      await asyncio.sleep(.15)
      after=await observe(mode+'-menu-before-activation')
      record(mode+'-awaits-explicit-intent',response['effect']=='dispatched' and original.read_bytes()==payload and (destination.read_bytes()==conflict if target_inode else not destination.exists()),tool_effect=response['effect'])
      if mode=='copy':
       popup=next(p for p in after['popups'] if p['owner_window_id']==tid);mb=popup['image_bounds']
       denied=await session.call_tool('desktop_click',dict(window_id=tid,snapshot_id=after['snapshot_id'],x=mb['x']+mb['width']/2,y=mb['y']+16))
       error=json.loads(denied.content[0].text)
       record('inactive-destination-menu-click-refused',denied.isError and error.get('code')=='FOCUS_CHANGED' and original.read_bytes()==payload and not destination.exists(),code=error.get('code'))
      before_popup=next(p for p in after['popups'] if p['owner_window_id']==tid)
      await call('desktop_activate',window_id=tid)
      after=await observe(mode+'-menu')
      popups=[p for p in after['popups'] if p['owner_window_id']==tid]
      if len(popups)!=1:raise RuntimeError('Expected one observed destination-owned native menu')
      popup=popups[0];mb=popup['bounds']
      if any(popup[key]!=before_popup[key] for key in ('xid','pid','start','generation','owner_window_id','transient_for','bounds')):raise RuntimeError('Native menu identity or geometry changed after activation')
      # Retained real Thunar 4.18 screenshot has Copy/Move/Link/Cancel rows.
      # These native-pixel offsets belong only to this fixed GTK theme fixture.
      # Use fresh popup origin and screenshot scale, never global coordinates.
      if (mb['width'],mb['height'])!=(129,117):raise RuntimeError('Observed native menu geometry changed; review screenshot before updating fixture')
      yoff=(18,45,72,100)[row]
      await call('desktop_click',window_id=tid,snapshot_id=after['snapshot_id'],x=(mb['x']+mb['width']/2)*sx,y=(mb['y']+yoff)*sy)
      if mode=='conflict-cancel':
       async def conflict_dialog():
        return next((w for w in (await call('desktop_windows'))['windows'] if w['pid']==src['pid'] and w['active'] and w['window_id'] not in (sid,tid)),None)
       dialog=await wait(conflict_dialog);dw=dialog['window_id']
       tree=await call('desktop_inspect',window_id=dw,limit=500)
       (OUT/'conflict-dialog-tree.json').write_text(json.dumps(tree,indent=2));await observe('conflict-dialog')
       cancel=next(n for n in tree['nodes'] if n['role']=='push button' and n['name'].replace('_','')=='Cancel' and 'showing' in n['states'])
       record('conflict-dialog-before-cancel',any('Replace' in n['name'] for n in tree['nodes']) and original.read_bytes()==payload and destination.read_bytes()==conflict)
       await call('desktop_invoke',element_id=cancel['element_id'],action=cancel['actions'][0])
       await call('desktop_wait',condition='window_absent',window_id=dw,timeout=4)
      async def settled():
       if mode=='move':return not original.exists() and destination.exists()
       if mode=='copy':return destination.exists()
       if mode=='link':return destination.is_symlink()
       return not (await call('desktop_observe'))['popups']
      await wait(settled)
      await asyncio.sleep(.15)
      source_ok=original.is_file() and original.read_bytes()==payload and original.stat().st_ino==source_inode
      if mode=='copy':passed=source_ok and destination.read_bytes()==payload and not destination.is_symlink() and destination.stat().st_ino!=source_inode
      elif mode=='move':passed=not original.exists() and destination.read_bytes()==payload and not destination.is_symlink() and destination.stat().st_ino==source_inode
      elif mode=='link':passed=source_ok and destination.is_symlink() and destination.resolve()==original.resolve() and destination.read_bytes()==payload
      elif mode=='cancel':passed=source_ok and not list(target.iterdir())
      else:passed=source_ok and destination.read_bytes()==conflict and destination.stat().st_ino==target_inode and sorted(p.name for p in target.iterdir())==['proof.bin']
      record(mode+'-filesystem-oracle',passed,source_exists=original.exists(),target_exists=destination.exists(),target_symlink=destination.is_symlink())
      await observe(mode+'-after-action')
      for wid in (sid,tid):await call('desktop_window',window_id=wid,action='close')
 except Exception as exc:
  import traceback
  (OUT/'traceback.txt').write_text(traceback.format_exc()); record('harness-failure',False,error=type(exc).__name__,message=str(exc))
 finally:
  for p in processes:
   if p.poll() is None:p.terminate();p.wait(timeout=3)
  (OUT/'results.json').write_text(json.dumps(dict(uid=os.getuid(),thunar_version=subprocess.run(['thunar','--version'],capture_output=True,text=True,timeout=3).stdout.splitlines(),cases=records),indent=2)+'\n')
 return 0 if records and all(r['passed'] for r in records) else 1
if __name__=='__main__':raise SystemExit(asyncio.run(main()))
