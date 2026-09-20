"""Private real-locale GTK data entry through public stdio MCP."""
import asyncio,gzip,json,os,signal,subprocess,sys,tempfile,time
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
ROOT=Path(__file__).resolve().parents[1]


async def child():
 with tempfile.TemporaryDirectory(prefix='luda-data-oracle-') as directory:
  out=Path(directory);wm=subprocess.Popen(['xfwm4','--compositor=off'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);fixture=None
  try:
   end=time.monotonic()+5
   while subprocess.run(['wmctrl','-m'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:
    assert time.monotonic()<end;await asyncio.sleep(.05)
   fixture=subprocess.Popen(['/usr/bin/python3',str(ROOT/'tests/data_entry_fixture.py'),directory])
   async def oracle(predicate):
    end=time.monotonic()+3
    while time.monotonic()<end:
     try:
      value=json.loads((out/'state.json').read_text())
      if predicate(value):return value
     except (FileNotFoundError,json.JSONDecodeError):pass
     await asyncio.sleep(.02)
    raise AssertionError('Independent data oracle did not reach requested state')
   async with stdio_client(StdioServerParameters(command=sys.executable,args=['-m','luda.server'],env=dict(os.environ))) as streams:
    async with ClientSession(*streams) as session:
     await session.initialize()
     async def call(name,error=None,**args):
      response=await session.call_tool(name,args);value=json.loads(response.content[0].text)
      if error:assert response.isError and value['code']==error,(name,value)
      else:assert not response.isError,(name,value)
      return value
     owner=None
     for _ in range(100):
      owner=next((w for w in (await call('desktop_windows'))['windows'] if w['pid']==fixture.pid),None)
      if owner:break
      await asyncio.sleep(.05)
     assert owner;wid=owner['window_id'];await call('desktop_activate',window_id=wid)
     tree=await call('desktop_inspect',window_id=wid,limit=200)
     nodes={node['name']:node for node in tree['nodes'] if node['name']};cases=[]
     async def entry(name,text):return await call('desktop_type',element_id=nodes[name]['element_id'],text=text,mode='replace')
     async def key(chord,count=1):return await call('desktop_press_keys',window_id=wid,chord=chord,count=count)
     async def focus(name):return await call('desktop_focus_element',element_id=nodes[name]['element_id'])
     async def submit():return await call('desktop_invoke',element_id=nodes['Submit data']['element_id'],action='click')
     initial=await oracle(lambda value:True)
     assert initial['decimal_point']==',' and initial['timezone']=='Europe/Berlin' and initial['amount_text']=='10,00'
     assert nodes['Locale amount']['value']=={'current':10.0,'minimum':0.0,'maximum':100.0,'increment':.01}
     observation=await session.call_tool('desktop_observe',{})
     snapshot=json.loads(next(content.text for content in observation.content if content.type=='text'))
     # Fixed owned GTK theme: visible March 29 is the Sunday in the penultimate
     # row. Read the screenshot first; the app file independently proves date.
     bounds=nodes['Date calendar']['bounds'];x=bounds['x']+bounds['width']*6.5/7;y=bounds['y']+bounds['height']-36
     sx=snapshot['image_size']['width']/snapshot['desktop_size']['width'];sy=snapshot['image_size']['height']/snapshot['desktop_size']['height']
     await call('desktop_click',window_id=wid,snapshot_id=snapshot['snapshot_id'],x=x*sx,y=y*sy)
     await oracle(lambda value:value['calendar']==[2026,3,29] and value['date_text']=='29.03.2026 12:30')
     await key('Right');await key('space');await oracle(lambda value:value['calendar']==[2026,3,30])
     cases.append('calendar-observed-point-and-explicit-focused-day-keyboard-selection')
     for boundary,chord,formatted in ((0,'Down','0,00'),(100,'Up','100,00')):
      await call('desktop_set_value',element_id=nodes['Locale amount']['element_id'],value=boundary)
      await focus('Locale amount');await key(chord)
      await oracle(lambda value:value['amount']==boundary and value['amount_text']==formatted)
     result=await call('desktop_set_value',element_id=nodes['Locale amount']['element_id'],value=12.345)
     assert result['effect']=='verified' and result['actual_value']==12.345
     await oracle(lambda value:value['amount']==12.345 and value['amount_text']=='12,35')
     text=await call('desktop_read_text',element_id=nodes['Locale amount']['element_id']);assert text['text']=='12,35'
     await call('desktop_invoke',element_id=nodes['Locale amount']['element_id'],action='activate')
     await oracle(lambda value:value['amount']==12.35 and value['submits']==0)
     for number in (-1,101):
      refused=await call('desktop_set_value',error='OUT_OF_BOUNDS',element_id=nodes['Locale amount']['element_id'],value=number)
      assert refused['effect']=='none'
     await oracle(lambda value:value['amount']==12.35)
     failed=await call('desktop_type',error='TEXT_MISMATCH',element_id=nodes['Locale amount']['element_id'],text='12,345',mode='replace')
     assert failed['effect']=='uncertain';await oracle(lambda value:value['amount_text']=='' and value['submits']==0)
     # A new explicit test case, not an automatic retry of the rejected edit.
     await focus('Locale amount');await entry('Locale amount','12,34');await key('Tab')
     await oracle(lambda value:value['amount']==12.34 and value['amount_text']=='12,34')
     cases.append('numeric-provider-value-versus-formatted-rounding-range-and-rejected-overprecision')
     invalid=[('31.02.2026 12:30','day is out of range'),('2026-03-29 03:30','does not match format'),('29.03.2026 02:30','does not exist'),('25.10.2026 02:30','ambiguous')]
     for index,(value,message) in enumerate(invalid,1):
      changed=await entry('Local date and time',value);assert changed['effect']=='verified'
      result=await submit();assert result['effect']=='dispatched'
      state=await oracle(lambda value:value['submits']==index)
      assert state['accepted']==0 and state['committed'] is None and message in state['validation']
      error_text=await call('desktop_read_text',element_id=nodes['Validation result']['element_id'])
      assert error_text['text']==state['validation']
     cases.append('explicit-submit-invalid-date-locale-dst-gap-and-fold-errors-observed')
     await entry('Local date and time','28.03.2026 12:30');await focus('Destination');await entry('Destination','Ber');await key('Escape')
     result=await submit();assert result['effect']=='dispatched'
     state=await oracle(lambda value:value['accepted']==1)
     assert state['committed']=={'utc':'2026-03-28T11:30:00+00:00','amount':12.34,'amount_text':'12,34','destination':'Ber','selected_suggestion':None}
     cases.append('literal-prefix-preserved-without-suggestion-selection-and-cet-utc-commit')
     await entry('Local date and time','29.03.2026 03:30');await focus('Destination')
     await entry('Destination','Be')
     await call('desktop_select',element_id=nodes['Destination']['element_id'],start_offset=2,end_offset=2)
     await key('r');await asyncio.sleep(.4)
     popup_observation=await session.call_tool('desktop_observe',{})
     assert any(content.type=='image' for content in popup_observation.content)
     # Screenshot shows Berlin, Bern, Bergen in this fixed fixture; choose Bern.
     await key('Down',2);await key('Return')
     state=await oracle(lambda value:value['selection_count']==1)
     assert state['selected_suggestion']=='Bern, Switzerland' and state['destination']=='Bern, Switzerland' and state['submits']==5
     readback=await call('desktop_read_text',element_id=nodes['Destination']['element_id']);assert readback['text']=='Bern, Switzerland'
     await submit();state=await oracle(lambda value:value['accepted']==2)
     assert state['committed']['utc']=='2026-03-29T01:30:00+00:00' and state['committed']['selected_suggestion']=='Bern, Switzerland'
     cases.append('observed-autocomplete-explicit-selection-readback-no-implicit-submit-and-cest-utc-commit')
     await entry('Destination','Berlin? keep literal');await key('Escape');await submit()
     state=await oracle(lambda value:value['accepted']==3)
     assert state['committed']['destination']=='Berlin? keep literal' and state['committed']['selected_suggestion'] is None and state['selection_count']==1 and state['submits']==7
     cases.append('editing-suggestion-back-to-literal-clears-selection-without-autocompletion')
     result={'suite':'gtk-data-entry','uid':os.getuid(),'locale':'de_DE.UTF-8','timezone':'Europe/Berlin','cases':cases,'passed':len(cases),'limits':['Fixed GTK fixture/theme only; calendar day cells and completion rows are absent from this owner accessibility tree.','Text readback is not date validity, numeric commit or suggestion selection.','No universal date parser, rounding normalization, implicit submission or retry.']}
     output=ROOT/'artifacts/data-entry';output.mkdir(parents=True,exist_ok=True);(output/'results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
  finally:
   if fixture and fixture.poll() is None:fixture.terminate();fixture.wait(timeout=3)
   if wm.poll() is None:wm.terminate();wm.wait(timeout=3)


def main():
 if os.getuid()==0:raise SystemExit('Run this qualification as the ordinary desktop account, for example through luda-session.')
 if '--child' in sys.argv:return asyncio.run(child())
 with tempfile.TemporaryDirectory(prefix='luda-private-data-session-') as directory:
  base=Path(directory);env=dict(os.environ)
  for key in ('XDG_CONFIG_HOME','XDG_DATA_HOME','XDG_CACHE_HOME','XDG_RUNTIME_DIR'):
   path=base/key;path.mkdir(mode=0o700);env[key]=str(path)
  env['XDG_CONFIG_DIRS']=env['XDG_CONFIG_HOME']
  source=Path(env.get('LUDA_TEST_I18N_SOURCE','/usr/share/i18n'))
  if not (source/'locales/de_DE').is_file():raise SystemExit('Install distro locales sources, or set LUDA_TEST_I18N_SOURCE to an extracted /usr/share/i18n; this test downloads nothing.')
  locales=base/'locales';locales.mkdir()
  charmap=base/'UTF-8';charmap.write_bytes(gzip.decompress((source/'charmaps/UTF-8.gz').read_bytes()))
  subprocess.run(['localedef','--no-archive','-i',str(source/'locales/de_DE'),'-f',str(charmap),str(locales/'de_DE.UTF-8')],env=dict(env,I18NPATH=str(source)),check=True,timeout=20,capture_output=True)
  env.update(LOCPATH=str(locales),LANG='de_DE.UTF-8',LC_ALL='de_DE.UTF-8',TZ='Europe/Berlin')
  process=subprocess.Popen(['xvfb-run','-a','-s','-screen 0 1200x900x24','dbus-run-session','--',sys.executable,__file__,'--child'],env=env,start_new_session=True)
  try:code=process.wait(timeout=50)
  finally:
   try:os.killpg(process.pid,signal.SIGTERM)
   except ProcessLookupError:pass
   try:process.wait(timeout=3)
   except subprocess.TimeoutExpired:pass
   try:os.killpg(process.pid,signal.SIGKILL)
   except ProcessLookupError:pass
   process.wait(timeout=3)
 raise SystemExit(code)

if __name__=='__main__':main()
