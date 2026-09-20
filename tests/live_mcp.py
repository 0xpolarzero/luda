"""Protocol-level integration against an independent GTK fixture, with real stdio MCP."""
import asyncio
import argparse
import base64
import io
from importlib.metadata import version
import json
import os
from pathlib import Path
import subprocess
import time

from PIL import Image
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts'/'mcp';OUT.mkdir(exist_ok=True)
results=[]

def record(name,ok,details=None):
 results.append({'case':name,'passed':bool(ok),'details':details})
 assert ok,(name,details)

async def main():
 p=subprocess.Popen(['/usr/bin/python3',str(ROOT/'tests/fixture.py'),str(OUT)])
 try:
  params=StdioServerParameters(command=args.server,env=dict(os.environ))
  async with stdio_client(params) as streams:
   async with ClientSession(*streams) as s:
    initialization=await s.initialize()
    record('mcp-product-version',initialization.serverInfo.name=='luda' and initialization.serverInfo.version==version('luda'))
    tools=(await s.list_tools()).tools
    (OUT/'tools.json').write_text(json.dumps([t.model_dump() for t in tools],indent=2))
    record('mcp-discovery',{'desktop_type','desktop_paste','desktop_press_keys','desktop_observe'} <= {t.name for t in tools})
    async def call(name,**args):
     r=await s.call_tool(name,args)
     assert not r.isError,(name,r)
     return json.loads(r.content[0].text),r
    d,_=await call('desktop_doctor');record('mcp-doctor',d['ready'])
    ws,_=await call('desktop_windows');w=next(w for w in ws['windows'] if w['pid']==p.pid);wid=w['window_id']
    await call('desktop_activate',window_id=wid)
    tree,_=await call('desktop_inspect',window_id=wid)
    button=next(n for n in tree['nodes'] if n['name']=='Record action')
    invocation=next(t for t in tools if t.name=='desktop_invoke')
    record('mcp-invoke-action-optional','action' not in invocation.inputSchema.get('required',[]))
    for count,extra in enumerate(({}, {'action':None}, {'action':button['actions'][0]}),1):
     invoked,_=await call('desktop_invoke',element_id=button['element_id'],**extra)
     end=time.monotonic()+2
     while json.loads((OUT/'state.json').read_text())['clicks']!=count:
      assert time.monotonic()<end,'Independent invoke counter did not advance'
      await asyncio.sleep(.02)
     record('mcp-invoke-exactly-once-'+str(count),invoked['effect']=='dispatched')
    rejected=await s.call_tool('desktop_invoke',{'element_id':button['element_id'],'action':'unobserved-action'})
    record('mcp-invoke-unobserved-action-refused',rejected.isError and json.loads(rejected.content[0].text)['code']=='UNSUPPORTED_ACTION' and json.loads((OUT/'state.json').read_text())['clicks']==3)
    n=next(n for n in tree['nodes'] if n['name']=='Contract text');eid=n['element_id']
    payload='MCP literal text\n日本語 👩🏽\u200d💻\n\tindent\n\n'
    value,_=await call('desktop_type',element_id=eid,text=payload,mode='replace')
    await asyncio.sleep(.1)
    actual=json.loads((OUT/'state.json').read_text())['text']
    record('mcp-set-text-readback',value['effect']=='verified' and actual==payload)
    value,_=await call('desktop_read_text',element_id=eid)
    record('mcp-read-text',value['text']==payload and not value['truncated'])
    shot,r=await call('desktop_observe',max_width=800)
    image=next(c for c in r.content if c.type=='image')
    raw=base64.b64decode(image.data);(OUT/'screen.png').write_bytes(raw)
    with Image.open(io.BytesIO(raw)) as im:record('mcp-image-metadata',im.size==(shot['image_size']['width'],shot['image_size']['height']))
    bad=await s.call_tool('desktop_click',{'window_id':wid,'snapshot_id':shot['snapshot_id'],'x':-1,'y':20})
    record('mcp-error-contract',bad.isError and json.loads(bad.content[0].text)['code']=='OUT_OF_BOUNDS')
    bad=await s.call_tool('desktop_click',{'window_id':wid,'snapshot_id':shot['snapshot_id'],'x':10,'y':20,'count':10000})
    record('mcp-schema-validation',bad.isError)
    for name,arguments in [
     ('desktop_click',{'window_id':wid,'snapshot_id':shot['snapshot_id'],'x':True,'y':20}),
     ('desktop_click',{'window_id':wid,'snapshot_id':shot['snapshot_id'],'x':10,'y':20,'count':True}),
     ('desktop_type',{'element_id':eid,'text':'must not be inserted','mdoe':'replace'}),
    ]:
     rejected=await s.call_tool(name,arguments)
     error=json.loads(rejected.content[0].text)
     record('mcp-strict-input-'+name,rejected.isError and error['code']=='INVALID_ARGUMENT' and error['effect']=='none')
    record('mcp-invalid-mutation-left-text-unchanged',json.loads((OUT/'state.json').read_text())['text']==payload)
    # Separate insertion from replacement through actual MCP calls.
    await call('desktop_type',element_id=eid,text='',mode='replace')
    await call('desktop_focus_element',element_id=eid)
    value,_=await call('desktop_paste',window_id=wid,text=payload,shortcut='ctrl_v')
    await asyncio.sleep(.15)
    record('mcp-paste-independent-readback',json.loads((OUT/'state.json').read_text())['text']==payload and value['effect']=='dispatched')
 finally:
  p.terminate();p.wait(timeout=3)
  (OUT/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
  print(json.dumps(results,ensure_ascii=False))

parser=argparse.ArgumentParser();parser.add_argument('--server',default=str(ROOT/'.venv/bin/luda'));args=parser.parse_args()
asyncio.run(main())
