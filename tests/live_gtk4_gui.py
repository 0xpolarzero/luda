"""Explicit GUI alternatives for two unsupported GTK4 semantic workflows."""
import argparse,asyncio,base64,json,os,subprocess,sys,tempfile,time,uuid
from pathlib import Path
from PIL import Image,ImageChops
import live_mcp_disconnect as transport
from live_mcp_disconnect import wait
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from qualification_matrix import private_environment,cleanup_owned
from headless_tests import stop
from qualify import source_fingerprint

async def child(out):
 transport.OUT=out;source=source_fingerprint(ROOT);records=[];limits=[];wm=None;app=None;client=None
 def state():return json.loads((out/'state.json').read_text())
 def record(case,passed,**detail):
  row=dict(case=case,passed=bool(passed),**detail);records.append(row);print(json.dumps(row),flush=True);assert passed,row
 try:
  with (out/'desktop.log').open('w') as log:
   wm=subprocess.Popen(['xfwm4','--compositor=off'],stdout=log,stderr=log)
   await wait(lambda:subprocess.run(['wmctrl','-m'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0)
   app=subprocess.Popen(['/usr/bin/python3',str(ROOT/'tests/gtk4_fixture.py'),str(out)],env=dict(os.environ,GTK_A11Y='atspi'),stdout=log,stderr=log)
   client=await transport.Client('mcp').start()
   async def call(name,allow_error=False,**args):
    reply=(await client.request('tools/call',{'name':name,'arguments':args}))['result']
    data=json.loads(next(c['text'] for c in reply['content'] if c['type']=='text'))
    with (out/'tools.jsonl').open('a') as log:log.write(json.dumps({'name':name,'arguments':args,'result':data})+'\n')
    assert allow_error or not reply.get('isError'),(name,data)
    return data,reply
   async def observe(label):
    snap,reply=await call('desktop_observe')
    (out/(label+'.png')).write_bytes(base64.b64decode(next(c['data'] for c in reply['content'] if c['type']=='image')))
    return snap
   wid=None
   for _ in range(100):
    windows,_=await call('desktop_windows');owner=next((w for w in windows['windows'] if w['pid']==app.pid),None)
    if owner:wid=owner['window_id'];break
    await asyncio.sleep(.05)
   assert wid;await call('desktop_activate',window_id=wid);await asyncio.sleep(.3)
   tree,_=await call('desktop_inspect',window_id=wid)
   nodes={}
   for node in tree['nodes']:nodes.setdefault(node['name'],node)
   (out/'inspect.json').write_text(json.dumps(tree,indent=2))
   check=nodes['Toolkit check'];editor=nodes['Toolkit text']
   refused,_=await call('desktop_set_checked',allow_error=True,element_id=check['element_id'],checked=True)
   limits.append({'operation':'semantic-checkbox','response':refused,'independent_state_after':state()})
   assert refused.get('code')=='UNSUPPORTED_ACTION' and state()['checked'] is False,refused
   snap=await observe('unchecked')
   bounds=next(w['image_bounds'] for w in snap['windows'] if w['window_id']==wid)
   assert bounds['width']==620 and bounds['height']==480,bounds
   x,y=bounds['x']+12,bounds['y']+298
   await call('desktop_click',window_id=wid,snapshot_id=snap['snapshot_id'],x=x,y=y)
   await wait(lambda:state()['checked'] is True)
   await observe('checked')
   before=Image.open(out/'unchecked.png').crop((x-8,y-8,x+8,y+8))
   after=Image.open(out/'checked.png').crop((x-8,y-8,x+8,y+8))
   record('explicit-observed-checkbox-click-checks-widget',bool(ImageChops.difference(before,after).getbbox()),independent_state=state(),screenshot_point=[x,y])
   current,_=await call('desktop_inspect',window_id=wid)
   current_check=next(n for n in current['nodes'] if n['name']=='Toolkit check')
   record('checked-state-visible-in-fresh-inspection','checked' in current_check['states'],states=current_check['states'])
   snap=await observe('checked-before-uncheck')
   await call('desktop_click',window_id=wid,snapshot_id=snap['snapshot_id'],x=x,y=y)
   await wait(lambda:state()['checked'] is False);await observe('unchecked-again')
   record('explicit-observed-checkbox-click-unchecks-widget',state()['checked'] is False)
   await call('desktop_type',element_id=editor['element_id'],text='prefix SUFFIX',mode='replace')
   await wait(lambda:state()['text']=='prefix SUFFIX')
   selection_before=state()
   failed,_=await call('desktop_select',allow_error=True,element_id=editor['element_id'],start_offset=7,end_offset=13)
   await asyncio.sleep(.1);selection_after=state()
   limits.append({'operation':'semantic-text-selection','response':failed,'independent_state_before':selection_before,'independent_state_after':selection_after})
   assert failed.get('code')=='ACCESSIBILITY_ERROR',failed
   assert selection_after['text']=='prefix SUFFIX'
   snap=await observe('semantic-selection-failed')
   await call('desktop_click',window_id=wid,snapshot_id=snap['snapshot_id'],x=bounds['x']+80,y=bounds['y']+50)
   await call('desktop_press_keys',window_id=wid,chord='ctrl+End')
   await call('desktop_press_keys',window_id=wid,chord='ctrl+shift+Left')
   await wait(lambda:state()['selection']==[7,13])
   await observe('keyboard-selected-suffix')
   record('explicit-keyboard-selects-exact-suffix',state()['selection']==[7,13],independent_state=state())
   replacement='日本語 👩🏽\u200d💻\n\t'
   await call('desktop_paste',window_id=wid,text=replacement)
   expected='prefix '+replacement
   await wait(lambda:state()['text']==expected)
   readback,_=await call('desktop_read_text',element_id=editor['element_id'])
   await observe('replacement-visible')
   record('GUI-paste-replaces-only-selected-suffix',readback['text']==expected and state()['text']==expected and state()['selection']==[],public_readback=readback,independent_state=state())
 except Exception as exc:records.append({'case':'harness-failure','passed':False,'error_type':type(exc).__name__,'message':str(exc)})
 finally:
  if client:
   await client.close()
   if client.forced_shutdown:records.append({'case':'forced-harness-cleanup','passed':False})
  for p in (app,wm):
   if p and p.poll() is None:p.terminate();p.wait(timeout=3)
  after=source_fingerprint(ROOT);result={'status':'passed' if records and all(r['passed'] for r in records) and source==after else 'failed','uid':os.getuid(),'cases':records,'preserved_semantic_limits':limits,'source_before':source,'source_after':after,'source_unchanged':source==after}
  (out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
 return 0 if result['status']=='passed' else 1

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path);p.add_argument('--child',action='store_true');args=p.parse_args()
 if os.getuid()==0:p.error('Run as ordinary desktop account.')
 out=(args.output or ROOT/'artifacts/gtk4-gui'/('run-'+str(time.time_ns()))).resolve();out.mkdir(parents=True,exist_ok=True)
 if args.child:return asyncio.run(child(out))
 token=str(uuid.uuid4())
 with tempfile.TemporaryDirectory(prefix='luda-private-gtk4-gui-') as directory:
  env=private_environment(Path(directory),token)
  with (out/'harness.log').open('w') as log:
   process=subprocess.Popen(['xvfb-run','-a','-s','-screen 0 1200x900x24 -nolisten tcp','dbus-run-session','--',sys.executable,__file__,'--child','--output',str(out)],env=env,stdout=log,stderr=log,start_new_session=True)
   try:code=process.wait(timeout=50)
   finally:stop(process);cleanup=cleanup_owned(token);(out/'cleanup.json').write_text(json.dumps(cleanup,indent=2)+'\n')
  assert not cleanup['survivors'],cleanup
 print(json.dumps({'output':str(out),'returncode':code,'cleanup':cleanup}));return code

if __name__=='__main__':raise SystemExit(main())
