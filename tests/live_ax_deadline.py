"""Public MCP inspect deadline against an actually stopped owned GTK provider."""
import argparse,asyncio,json,os,signal,subprocess,sys,tempfile,time,uuid
from pathlib import Path
import live_mcp_disconnect as transport
from live_mcp_disconnect import wait,process_identities,alive
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from qualification_matrix import private_environment,cleanup_owned
from headless_tests import stop
from qualify import source_fingerprint

async def child(out):
 transport.OUT=out;source=source_fingerprint(ROOT);records=[];app=None;wm=None;client=None;stopped=False
 def record(case,passed,**details):
  row=dict(case=case,passed=bool(passed),**details);records.append(row);print(json.dumps(row),flush=True);assert passed,row
 def state():return json.loads((out/'state.json').read_text())
 try:
  with (out/'desktop.log').open('w') as log:
   wm=subprocess.Popen(['xfwm4','--compositor=off'],stdout=log,stderr=log)
   await wait(lambda:subprocess.run(['wmctrl','-m'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0)
   app=subprocess.Popen(['/usr/bin/python3',str(ROOT/'tests/fixture.py'),str(out)],stdout=log,stderr=log)
   client=await transport.Client('mcp').start()
   wid=None
   for _ in range(100):
    windows=(await client.call('desktop_windows'))['windows'];owner=next((w for w in windows if w['pid']==app.pid),None)
    if owner:wid=owner['window_id'];break
    await asyncio.sleep(.05)
   assert wid
   await client.call('desktop_activate',window_id=wid)
   tree=await client.call('desktop_inspect',window_id=wid)
   entry=next(n for n in tree['nodes'] if n['name']=='Contract text')
   await client.call('desktop_type',element_id=entry['element_id'],text='Unchanged during stopped-provider inspection 日本語',mode='replace')
   await wait(lambda:(out/'state.json').exists() and state()['text']=='Unchanged during stopped-provider inspection 日本語')
   baseline=state();record('healthy-accessibility-and-independent-baseline',bool(tree['nodes']),node_count=len(tree['nodes']))
   os.kill(app.pid,signal.SIGSTOP);stopped=True
   await wait(lambda:Path('/proc',str(app.pid),'stat').read_text().rsplit(')',1)[1].split()[0]=='T')
   began=time.monotonic();pending=await client.begin('tools/call',{'name':'desktop_inspect','arguments':{'window_id':wid,'limit':500}})
   workers={}
   async def capture():
    while not pending.done():
     for pid,start in process_identities(client.process.pid).items():
      try:
       if b'ax_worker.py' in Path('/proc',str(pid),'cmdline').read_bytes():workers[pid]=start
      except FileNotFoundError:pass
     await asyncio.sleep(.005)
   sampler=asyncio.create_task(capture())
   try:
    # This watchdog does not cancel the request; a miss fails the test. The
    # actual worker has 5s plus at most 1s reap, with 1s transport/setup margin.
    done,_=await asyncio.wait({pending},timeout=7)
    elapsed=time.monotonic()-began
    record('entire-inspect-call-completes-without-client-cancellation',bool(done),seconds=elapsed,watchdog_seconds=7,provider_still_stopped=Path('/proc',str(app.pid),'stat').read_text().rsplit(')',1)[1].split()[0]=='T')
    reply=pending.result()['result'];payload=json.loads(reply['content'][0]['text'])
    record('stopped-provider-response-is-typed-no-effect',reply.get('isError') and payload.get('code') in ('TIMEOUT','ACCESSIBILITY_UNAVAILABLE','ACCESSIBILITY_ERROR') and payload.get('effect')=='none',code=payload.get('code'),effect=payload.get('effect'),message=payload.get('message'),seconds=elapsed)
   finally:
    sampler.cancel()
    try:await sampler
    except asyncio.CancelledError:pass
   await wait(lambda:not alive(workers),timeout=2)
   record('captured-AX-worker-exits-before-recovery',bool(workers) and not alive(workers),worker_identities=workers,surviving_workers=alive(workers),server_descendants=process_identities(client.process.pid))
   status_start=time.monotonic();status=await client.call('desktop_status')
   record('server-responsive-after-provider-failure',not status.get('recovering'),seconds=time.monotonic()-status_start)
   os.kill(app.pid,signal.SIGCONT);stopped=False
   recovered=await client.call('desktop_inspect',window_id=wid)
   record('same-MCP-session-fresh-inspect-recovers',any(n['name']=='Contract text' for n in recovered['nodes']),node_count=len(recovered['nodes']))
   await asyncio.sleep(.3)
   record('inspection-failure-and-resume-did-not-mutate-app',state()==baseline,independent_state=state())
 except Exception as exc:
  records.append({'case':'harness-failure','passed':False,'error_type':type(exc).__name__,'message':str(exc)})
 finally:
  if app and app.poll() is None:
   if stopped:os.kill(app.pid,signal.SIGCONT)
  if client:
   await client.close()
   if client.forced_shutdown:records.append({'case':'forced-harness-server-cleanup','passed':False})
  for process in (app,wm):
   if process and process.poll() is None:process.terminate();process.wait(timeout=3)
  after=source_fingerprint(ROOT)
  result={'status':'passed' if records and all(r['passed'] for r in records) and source==after else 'failed','uid':os.getuid(),'cases':records,'source_before':source,'source_after':after,'source_unchanged':source==after,
   'scope':'Owned GTK process stopped; no protocol cancellation, bus failure or whole-OS freeze.'}
  (out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
 return 0 if result['status']=='passed' else 1

def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path);parser.add_argument('--child',action='store_true');args=parser.parse_args()
 if os.getuid()==0:parser.error('Run as ordinary desktop account.')
 out=(args.output or ROOT/'artifacts/ax-deadline'/('run-'+str(time.time_ns()))).resolve();out.mkdir(parents=True,exist_ok=True)
 if args.child:return asyncio.run(child(out))
 token=str(uuid.uuid4())
 with tempfile.TemporaryDirectory(prefix='luda-private-ax-deadline-') as directory:
  env=private_environment(Path(directory),token)
  with (out/'harness.log').open('w') as log:
   process=subprocess.Popen(['xvfb-run','-a','-s','-screen 0 1200x900x24 -nolisten tcp','dbus-run-session','--',sys.executable,__file__,'--child','--output',str(out)],env=env,stdout=log,stderr=log,start_new_session=True)
   try:code=process.wait(timeout=35)
   finally:stop(process);cleanup=cleanup_owned(token);(out/'cleanup.json').write_text(json.dumps(cleanup,indent=2)+'\n')
  assert not cleanup['survivors'],cleanup
 print(json.dumps({'output':str(out),'returncode':code,'cleanup':cleanup}));return code

if __name__=='__main__':raise SystemExit(main())
