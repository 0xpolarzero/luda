"""Actual MCP OCR on owned GTK pixels, with independent text/geometry oracles."""
import asyncio,base64,json,os,subprocess,sys,time
from pathlib import Path
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts/ocr'/str(time.time_ns());OUT.mkdir(parents=True)
assert os.getuid()!=0 and os.environ.get('LUDA_ISOLATED_TEST_DISPLAY')=='1'

async def main():
 processes=[];results=[]
 try:
  wm=subprocess.Popen(['xfwm4','--compositor=off'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);processes.append(wm)
  for _ in range(80):
   if subprocess.run(['wmctrl','-m'],capture_output=True).returncode==0:break
   await asyncio.sleep(.05)
  fixture=subprocess.Popen(['/usr/bin/python3',str(ROOT/'tests/ocr_fixture.py'),str(OUT)]);processes.append(fixture)
  async with stdio_client(StdioServerParameters(command=sys.executable,args=['-m','luda.server'],env=dict(os.environ))) as streams:
   async with ClientSession(*streams) as client:
    await client.initialize()
    async def call(name,**args):
     response=await client.call_tool(name,args);assert not response.isError,(name,response)
     return json.loads(response.content[0].text),response
    for _ in range(80):
     windows,_=await call('desktop_windows');target=next((w for w in windows['windows'] if w['pid']==fixture.pid),None)
     if target and (OUT/'oracle.json').exists():break
     await asyncio.sleep(.05)
    assert target
    await call('desktop_activate',window_id=target['window_id']);await asyncio.sleep(.15)
    oracle=json.loads((OUT/'oracle.json').read_text());assert oracle['changed'] is False
    observed,response=await call('desktop_observe',max_width=900)
    image=next(c for c in response.content if c.type=='image');(OUT/'snapshot.png').write_bytes(base64.b64decode(image.data))
    (OUT/'change').touch()
    for _ in range(80):
     if json.loads((OUT/'oracle.json').read_text())['changed']:break
     await asyncio.sleep(.02)
    assert json.loads((OUT/'oracle.json').read_text())['changed']
    value,_=await call('desktop_ocr',snapshot_id=observed['snapshot_id'])
    assert value['effect']=='none' and value['snapshot_id']==observed['snapshot_id'] and 'uncalibrated' in value['confidence_semantics']
    scale_x=observed['image_size']['width']/observed['desktop_size']['width'];scale_y=observed['image_size']['height']/observed['desktop_size']['height']
    for expected in oracle['words']:
     candidate=next(c for c in value['candidates'] if c['text']==expected['text']);actual=candidate['image_bounds'];known=expected['bounds']
     for key,scale in [('x',scale_x),('y',scale_y),('width',scale_x),('height',scale_y)]:assert abs(actual[key]-known[key]*scale)<=5,(expected,candidate,key)
    assert not any(c['text']=='CHANGED' for c in value['candidates'])
    results.append({'case':'historical-pixels-exact-owned-words-and-pango-boxes','passed':True,'ocr':value,'oracle':oracle})
    response=await client.call_tool('desktop_ocr',{'snapshot_id':observed['snapshot_id'],'language':'luda_missing_model'})
    assert response.isError and json.loads(response.content[0].text)['code']=='OCR_LANGUAGE_UNAVAILABLE'
    doctor,_=await call('desktop_doctor');assert doctor['ready'];results.append({'case':'missing-language-does-not-break-backend','passed':True})
    await call('desktop_window',window_id=target['window_id'],action='move',x=100,y=100)
    response=await client.call_tool('desktop_ocr',{'snapshot_id':observed['snapshot_id']})
    assert response.isError and json.loads(response.content[0].text)['code']=='STALE_OBSERVATION'
    results.append({'case':'changed-layout-refuses-old-snapshot','passed':True})
 finally:
  for process in reversed(processes):
   if process.poll() is None:
    process.terminate()
    try:process.wait(timeout=3)
    except subprocess.TimeoutExpired:process.kill();process.wait()
  (OUT/'result.json').write_text(json.dumps({'cases':results,'tesseract_version':subprocess.check_output(['tesseract','--version'],text=True).splitlines()[0]},indent=2)+'\n')
 print(json.dumps(results))

asyncio.run(main())
