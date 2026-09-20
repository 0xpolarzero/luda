"""Actual GTK list/table ranges through public MCP with stable app-record oracles."""
import asyncio,json,os,subprocess,tempfile,time
from pathlib import Path
import live_mcp_disconnect as wire
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts/range-selection'
async def main():
 if os.getuid()==0 or os.environ.get('LUDA_ISOLATED_TEST_DISPLAY')!='1':raise RuntimeError('Private ordinary-account GUI required')
 OUT.mkdir(parents=True,exist_ok=True);wire.OUT=OUT;rows=[]
 def record(name,passed,**details):
  rows.append(dict(case=name,passed=bool(passed),**details));(OUT/'results.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))
  if not passed:raise AssertionError(name)
 def state():return json.loads((OUT/'state.json').read_text())
 async def until(predicate):
  end=time.monotonic()+3
  while time.monotonic()<end:
   try:
    value=predicate()
    if value:return value
   except (FileNotFoundError,json.JSONDecodeError):pass
   await asyncio.sleep(.025)
  raise AssertionError('Independent app oracle deadline')
 log=(OUT/'fixture.log').open('w');fixture=subprocess.Popen(['/usr/bin/python3',str(ROOT/'tests/data_fixture.py'),str(OUT),'range'],stdout=log,stderr=log,start_new_session=True);client=await wire.Client('mcp').start()
 async def call(tool,**arguments):
  response=(await client.request('tools/call',{'name':tool,'arguments':arguments}))['result'];result=json.loads(response['content'][0]['text'])
  if response.get('isError'):raise AssertionError((tool,result))
  return result
 async def denied(name,codes,**arguments):
  response=(await client.request('tools/call',{'name':name,'arguments':arguments}))['result'];result=json.loads(response['content'][0]['text'])
  record(name+'-refused',response.get('isError') and result['code'] in codes,response=result);return result
 try:
  wid=None
  for _ in range(100):
   windows=(await call('desktop_windows'))['windows'];found=[w for w in windows if w['pid']==fixture.pid]
   if found:wid=found[0]['window_id'];break
   await asyncio.sleep(.05)
  if wid is None:raise AssertionError('Fixture window absent')
  await call('desktop_activate',window_id=wid);await until(lambda:state().get('row_count')==120)
  async def inspect(kind='table'):
   result=await call('desktop_inspect',window_id=wid,role='table cell' if kind=='table' else 'list item',name='Record' if kind=='table' else 'Option',limit=100)
   (OUT/(kind+'-tree.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2));return {n['name']:n['element_id'] for n in result['nodes']}
  async def button(name):
   tree=await call('desktop_inspect',window_id=wid,name=name);node=next(n for n in tree['nodes'] if n['name']==name and n['role']=='push button')
   return await call('desktop_invoke',element_id=node['element_id'])
  async def choose(items,start,end,extend=False):return await call('desktop_choose',element_id=items[start],range_end_id=items[end],extend=extend)
  table=await inspect();result=await choose(table,'Record 0001','Record 0003');await until(lambda:state().get('selected_ids')==[1,2,3]);record('table-inclusive-range',result['effect']=='verified' and result['progress']['verified_completed']==3,response=result,oracle=state())
  result=await choose(table,'Record 0005','Record 0004',True);await until(lambda:state().get('selected_ids')==[1,2,3,4,5]);record('table-reversed-add',result['effect']=='verified',response=result,oracle=state())
  before=state()['selection_events'];result=await choose(table,'Record 0004','Record 0005',True);await asyncio.sleep(.08);record('table-idempotent',not result['changed'] and result['progress']['requested']==0 and state()['selection_events']==before)
  result=await choose(table,'Record 0002','Record 0003');await until(lambda:state().get('selected_ids')==[2,3]);record('table-exclusive-removes-others',result['progress']['verified_completed']==3,oracle=state())
  options=await inspect('list');result=await choose(options,'Option 01','Option 03');await until(lambda:state().get('option_ids')==[1,2,3]);record('list-inclusive-range',result['effect']=='verified',response=result,oracle=state())
  result=await choose(options,'Option 04','Option 03',True);await until(lambda:state().get('option_ids')==[1,2,3,4]);record('list-reversed-add',result['effect']=='verified',oracle=state())
  result=await choose(options,'Option 02','Option 03');await until(lambda:state().get('option_ids')==[2,3]);record('list-exclusive-verifies-clear-then-add',result['effect']=='verified' and result['progress']['verified_completed']==3,response=result,oracle=state())
  await button('Disable option two');before=state()['option_ids'];denial=await denied('desktop_choose',{'NOT_INTERACTABLE'},element_id=options['Option 01'],range_end_id=options['Option 03']);record('disabled-range-no-change',denial['effect']=='none' and state()['option_ids']==before)
  table=await inspect();before=state()['selected_ids'];denial=await denied('desktop_choose',{'NOT_INTERACTABLE'},element_id=table['Record 0030'],range_end_id=table['Record 0032']);record('offscreen-range-no-change',denial['effect']=='none' and state()['selected_ids']==before)
  await button('Open focus observer');await until(lambda:state().get('focus_window'))
  active_before=subprocess.check_output(['xdotool','getactivewindow'],text=True).strip()
  result=await choose(table,'Record 0001','Record 0003');await until(lambda:state()['selected_ids']==[1,2,3])
  active_after=subprocess.check_output(['xdotool','getactivewindow'],text=True).strip()
  record('background-range-preserves-foreground',result['effect']=='verified' and active_before==active_after,response=result,oracle=state())
  await call('desktop_activate',window_id=wid)
  old=table;await button('Reverse sort');denial=await denied('desktop_choose',{'STALE_TARGET','NOT_INTERACTABLE'},element_id=old['Record 0001'],range_end_id=old['Record 0003']);record('sort-old-range-refused',denial['effect']=='none')
  await button('Reset data');table=await inspect();await button('Filter first ten');denial=await denied('desktop_choose',{'STALE_TARGET','NOT_INTERACTABLE'},element_id=table['Record 0001'],range_end_id=table['Record 0003']);record('filter-old-range-refused',denial['effect']=='none')
  await button('Reset data');table=await inspect();await button('Sort during selection');denial=await denied('desktop_choose',{'STALE_TARGET','SELECTION_UNVERIFIABLE'},element_id=table['Record 0001'],range_end_id=table['Record 0003']);record('sort-during-range-stops',denial['effect']=='uncertain' and denial['details']['progress']['current_uncertain']==1,response=denial,oracle=state())
  await button('Reset data');await button('Duplicate row label');tree=await call('desktop_inspect',window_id=wid,role='table cell',name='Record',limit=100);nodes=tree['nodes'];first=next(n for n in nodes if n['name']=='Record 0001');last=next(n for n in nodes if n['name']=='Record 0003');before=state().get('selected_ids');denial=await denied('desktop_choose',{'UNSUPPORTED'},element_id=first['element_id'],range_end_id=last['element_id']);record('duplicate-label-range-no-change',denial['effect']=='none' and state().get('selected_ids')==before)
  await button('Reset data');table=await inspect();await button('Replace during selection');denial=await denied('desktop_choose',{'STALE_TARGET','SELECTION_UNVERIFIABLE'},element_id=table['Record 0001'],range_end_id=table['Record 0003']);record('recycle-during-range-stops',denial['effect']=='uncertain',response=denial,oracle=state())
  await button('Reset data');await button('Single selection mode');table=await inspect();denial=await denied('desktop_choose',{'SELECTION_UNVERIFIABLE'},element_id=table['Record 0005'],range_end_id=table['Record 0007']);await asyncio.sleep(.08);record('single-selection-stops-partial',denial['effect']=='uncertain' and denial['details']['progress']['current_uncertain']==1 and len(state()['selected_ids'])<=1,response=denial,oracle=state())
 finally:
  await client.close();fixture.terminate();fixture.wait(timeout=3);log.close()
 return 0
if __name__=='__main__':raise SystemExit(asyncio.run(main()))
