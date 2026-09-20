"""Actual MCP refusal of dead-key/Compose requests on private French XKB."""
import argparse,asyncio,json,os,subprocess,sys,tempfile,time,uuid
from pathlib import Path
import live_mcp_disconnect as transport
from live_mcp_disconnect import wait
from live_keyboard_guard import Oracle
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from qualification_matrix import private_environment,cleanup_owned
from headless_tests import stop
from qualify import source_fingerprint

async def child(out):
 transport.OUT=out;source=source_fingerprint(ROOT);records=[];app=None;wm=None;client=None;oracle=None;original=None
 def record(case,passed,**details):
  row=dict(case=case,passed=bool(passed),**details);records.append(row);print(json.dumps(row),flush=True);assert passed,row
 def state():return json.loads((out/'state.json').read_text())
 def keymap():return subprocess.check_output(['xkbcomp','-xkb',os.environ['DISPLAY'],'-'],stderr=subprocess.DEVNULL)
 try:
  with (out/'desktop.log').open('w') as log:
   wm=subprocess.Popen(['xfwm4','--compositor=off'],stdout=log,stderr=log)
   await wait(lambda:subprocess.run(['wmctrl','-m'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0)
   original=keymap()
   config=dict(line.split(':',1) for line in subprocess.check_output(['setxkbmap','-query'],text=True).splitlines());config={k.strip():v.strip() for k,v in config.items()}
   restore=['setxkbmap','-option','']
   for key in ('rules','model','layout','variant'):
    if config.get(key):restore += ['-'+key,config[key]]
   if config.get('options'):restore += ['-option',config['options']]
   subprocess.run(['setxkbmap','-layout','fr','-option','','-option','compose:ralt'],check=True)
   configured=keymap();oracle=Oracle()
   record('private-french-map-exposes-dead-key-and-compose',b'dead_circumflex' in configured and b'Multi_key' in configured and oracle.code('dead_circumflex')!=0 and oracle.code('Multi_key')!=0)
   app=subprocess.Popen(['/usr/bin/python3',str(ROOT/'tests/keyboard_fixture.py'),str(out)],stdout=log,stderr=log)
   client=await transport.Client('mcp').start();wid=None
   for _ in range(100):
    windows=(await client.call('desktop_windows'))['windows'];owner=next((w for w in windows if w['pid']==app.pid),None)
    if owner:wid=owner['window_id'];break
    await asyncio.sleep(.05)
   assert wid
   await client.call('desktop_activate',window_id=wid)
   await wait(lambda:(out/'state.json').exists())
   baseline=state();held=oracle.pressed();assert not held and not oracle.buttons()
   for chord in ('dead_circumflex','dead_acute','Multi_key','Compose',"Compose+apostrophe+e"):
    response=(await client.request('tools/call',{'name':'desktop_press_keys','arguments':{'window_id':wid,'chord':chord}}))['result']
    payload=json.loads(response['content'][0]['text']);await asyncio.sleep(.06)
    record('explicit-no-input-refusal-'+chord,response.get('isError') and payload.get('code')=='INVALID_KEY' and payload.get('effect')=='none' and state()==baseline and oracle.pressed()==held and not oracle.buttons(),response=payload,widget_unchanged=state()==baseline,held_keycodes=sorted(oracle.pressed()))
   tree=await client.call('desktop_inspect',window_id=wid)
   editor=next(n for n in tree['nodes'] if 'EditableText' in n['interfaces'])
   expected='é ê œ 日本語 👩🏽‍💻'
   typed=await client.call('desktop_type',element_id=editor['element_id'],text=expected,mode='replace')
   await wait(lambda:state()['text']==expected)
   read=await client.call('desktop_read_text',element_id=editor['element_id'])
   record('unicode-semantic-insertion-after-refusal',read['text']==expected and state()['text']==expected and not oracle.pressed() and not oracle.buttons(),public_effect=typed.get('effect'),independent_text=state()['text'])
   record('layout-unchanged-by-public-tools',keymap()==configured)
 except Exception as exc:records.append({'case':'harness-failure','passed':False,'error_type':type(exc).__name__,'message':str(exc)})
 finally:
  if client:
   await client.close()
   if client.forced_shutdown:records.append({'case':'forced-harness-server-cleanup','passed':False})
  if original is not None:
   subprocess.run(restore,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,check=True)
   restored=keymap();(out/'original.xkb').write_bytes(original);(out/'restored.xkb').write_bytes(restored)
   records.append({'case':'original-private-layout-restored','passed':restored==original})
  if oracle:oracle.close()
  for process in (app,wm):
   if process and process.poll() is None:process.terminate();process.wait(timeout=3)
  after=source_fingerprint(ROOT)
  result={'status':'passed' if records and all(r['passed'] for r in records) and source==after else 'failed','uid':os.getuid(),'cases':records,'source_before':source,'source_after':after,'source_unchanged':source==after,'scope':'Named dead-key and Compose requests are refused; Unicode text insertion is not compose-sequence support.'}
  (out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
 return 0 if result['status']=='passed' else 1

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path);parser.add_argument('--child',action='store_true');args=parser.parse_args()
 if os.getuid()==0:parser.error('Run as ordinary desktop account.')
 out=(args.output or ROOT/'artifacts/dead-compose'/('run-'+str(time.time_ns()))).resolve();out.mkdir(parents=True,exist_ok=True)
 if args.child:return asyncio.run(child(out))
 token=str(uuid.uuid4())
 with tempfile.TemporaryDirectory(prefix='luda-private-dead-compose-') as directory:
  env=private_environment(Path(directory),token)
  with (out/'harness.log').open('w') as log:
   process=subprocess.Popen(['xvfb-run','-a','-s','-screen 0 1200x900x24 -nolisten tcp','dbus-run-session','--',sys.executable,__file__,'--child','--output',str(out)],env=env,stdout=log,stderr=log,start_new_session=True)
   try:code=process.wait(timeout=35)
   finally:stop(process);cleanup=cleanup_owned(token);(out/'cleanup.json').write_text(json.dumps(cleanup,indent=2)+'\n')
  assert not cleanup['survivors'],cleanup
 print(json.dumps({'output':str(out),'returncode':code,'cleanup':cleanup}));return code

if __name__=='__main__':raise SystemExit(main())
