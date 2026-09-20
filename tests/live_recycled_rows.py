"""Public MCP scroll/reacquire across actual delayed GTK recycled rows."""
import asyncio,json,os,subprocess,time
from pathlib import Path
import live_mcp_disconnect as wire
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts/recycled-rows'
async def main():
 assert os.getuid()!=0 and os.environ.get('LUDA_ISOLATED_TEST_DISPLAY')=='1'
 OUT.mkdir(parents=True,exist_ok=True);wire.OUT=OUT;cases=[];responses=[]
 def record(name,okay,**details):
  cases.append(dict(case=name,passed=bool(okay),**details));(OUT/'results.json').write_text(json.dumps(cases,indent=2));assert okay,name
 def state():return json.loads((OUT/'state.json').read_text())
 async def until(predicate):
  end=time.monotonic()+4
  while time.monotonic()<end:
   try:
    s=state()
    if predicate(s):return s
   except (FileNotFoundError,json.JSONDecodeError):pass
   await asyncio.sleep(.03)
  raise AssertionError('App oracle deadline')
 log=(OUT/'fixture.log').open('w');fixture=subprocess.Popen(['/usr/bin/python3',str(ROOT/'tests/recycled_rows_fixture.py'),str(OUT)],stdout=log,stderr=log,start_new_session=True);client=await wire.Client('mcp').start()
 async def call(tool,allow_error=False,**args):
  raw=(await client.request('tools/call',{'name':tool,'arguments':args}))['result'];v=json.loads(raw['content'][0]['text']);responses.append({'tool':tool,'arguments':args,'response':v});(OUT/'responses.json').write_text(json.dumps(responses,indent=2))
  if not allow_error:assert not raw.get('isError'),(tool,v)
  return v
 try:
  wid=None
  for _ in range(100):
   found=[w for w in (await call('desktop_windows'))['windows'] if w['pid']==fixture.pid]
   if found:wid=found[0]['window_id'];break
   await asyncio.sleep(.05)
  assert wid;await call('desktop_activate',window_id=wid);await until(lambda s:s['visible_ids']==[0,1,2,3])
  async def tree():return await call('desktop_inspect',window_id=wid,role='table cell',limit=30)
  async def identity(number):
   t=await tree();return next(n for n in t['nodes'] if n['name']==f'Record {number:03}')
  async def button(name):
   t=await call('desktop_inspect',window_id=wid,name=name);n=next(n for n in t['nodes'] if n['role']=='push button' and n['name']==name);await call('desktop_invoke',element_id=n['element_id'])
  async def scroll():
   shot=await call('desktop_observe');w=next(w for w in shot['windows'] if w['window_id']==wid);b=w['image_bounds']
   await call('desktop_scroll',window_id=wid,snapshot_id=shot['snapshot_id'],x=b['x']+b['width']//2,y=b['y']+b['height']//2,direction='down',ticks=1)
  def paths():return json.loads(subprocess.check_output(['/usr/bin/python3',str(ROOT/'tests/recycled_rows_observer.py'),str(fixture.pid)],text=True,timeout=5))
  initial_paths=paths()
  old=await identity(1);before=state()['generation'];await scroll();await until(lambda s:s['generation']>before and not s['loading']);record('delayed-page-actually-loaded',state()['page']==1 and state()['visible_ids']==[4,5,6,7],oracle=state())
  next_paths=paths();prior=next(n for n in initial_paths if n['name']=='Record 001');fresh=next(n for n in next_paths if n['name']=='Record 005');record('same-provider-object-path-recycled',prior['path']==fresh['path'] and prior['provider']==fresh['provider'],before=prior,after=fresh)
  denied=await call('desktop_choose',True,element_id=old['element_id']);record('changed-record-old-handle-refused',denied.get('code')=='STALE_TARGET' and denied['effect']=='none' and state()['selected_id'] is None,response=denied)
  current=await tree();duplicate=[n for n in current['nodes'] if n['name']=='Duplicate'];record('duplicate-labels-observed',len(duplicate)==2)
  row=await identity(5);chosen=await call('desktop_choose',element_id=row['element_id']);await until(lambda s:s['selected_id']==5);record('reacquired-visible-record-selected',chosen['effect']=='verified',oracle=state())
  before=state()['generation'];await scroll();await until(lambda s:s['generation']>before and s['end']);row=await identity(9);await call('desktop_choose',element_id=row['element_id']);await until(lambda s:s['selected_id']==9);record('next-page-same-label-distinct-id',state()['visible_ids']==[8,9,10,11],oracle=state())
  generation=state()['generation'];requests=state()['scroll_requests'];await scroll();await asyncio.sleep(.6);tree_end=await call('desktop_inspect',window_id=wid,name='End of data');record('end-visible-no-new-records',state()['generation']==generation and state()['scroll_requests']>requests and any(n['name']=='End of data' for n in tree_end['nodes']))
  old=await identity(9);await button('Filter');await until(lambda s:s['filtered']);denied=await call('desktop_choose',True,element_id=old['element_id']);record('filter-old-handle-refused',denied.get('code')=='STALE_TARGET' and denied['effect']=='none',response=denied)
  row=await identity(102);await call('desktop_choose',element_id=row['element_id']);await until(lambda s:s['selected_id']==102);record('filtered-record-reacquired',True,oracle=state())
  await button('Reset');await button('Stall loading');initial=await tree();generation=state()['generation'];requests=state()['scroll_requests']
  for _ in range(2):await scroll();await asyncio.sleep(.6)
  final=await tree();record('bounded-no-progress-not-end',state()['generation']==generation and state()['scroll_requests']==requests+2 and not state()['end'] and [n['name'] for n in initial['nodes']]==[n['name'] for n in final['nodes']],oracle=state(),search_result='stopped_after_two_scrolls_without_progress_not_absent')
 finally:
  await client.close();fixture.terminate();fixture.wait(timeout=3);log.close()
 return 0
if __name__=='__main__':raise SystemExit(asyncio.run(main()))
