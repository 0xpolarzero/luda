"""Protocol-level integration against an independent GTK fixture, with real stdio MCP."""
import asyncio
import argparse
import base64
import io
import hashlib
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
    declarations=sorted([tool.model_dump(mode='json',exclude_none=True) for tool in tools],key=lambda tool:tool['name'])
    expected_schema=hashlib.sha256(json.dumps(declarations,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode('utf-8')).hexdigest()
    record('mcp-doctor-discovery-identity',d['versions']['driver_version']==initialization.serverInfo.version and d['versions']['tool_schema']['sha256']==expected_schema and d['versions']['bundled_skill']['status']=='identified')

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
    error=json.loads(bad.content[0].text)
    record('mcp-error-contract',bad.isError and error['code']=='OUT_OF_BOUNDS' and type(error.get('elapsed_ms')) is int and error['elapsed_ms']>=0)
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
    prior_operation=value['operation_id']
    report,response=await call('desktop_report')
    serialized=response.content[0].text
    record('mcp-report-bounded-correlation',report['schema_version']==1 and report['effect']=='none' and report['history_scope']=='current_mcp_process' and len(report['operations'])<=32 and any(row.get('operation_id')==prior_operation and row.get('method')=='paste' for row in report['operations']))
    record('mcp-report-content-free',len(response.content)==1 and response.content[0].type=='text' and all(sensitive not in serialized for sensitive in (payload,'MCP literal text','Contract text',str(ROOT),str(OUT),wid,eid,shot['snapshot_id'])) and all(set(row)<=set(('operation_id','method','effect','elapsed_ms','ok','code','action')) for row in report['operations']))
    record('mcp-report-health-and-no-input',report['health']['ready'] is True and json.loads((OUT/'state.json').read_text())['text']==payload)
    record('mcp-report-safe-error-action-and-identities',any(row.get('code')=='OUT_OF_BOUNDS' for row in report['operations']) and any(row.get('method')=='element' and row.get('action')=='invoke' for row in report['operations']) and report['versions']['tool_schema']['sha256']==expected_schema and report['versions']['bundled_skill']['sha256']==d['versions']['bundled_skill']['sha256'])


 finally:
  p.terminate();p.wait(timeout=3)
  (OUT/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
  print(json.dumps(results,ensure_ascii=False))

parser=argparse.ArgumentParser();parser.add_argument('--server',default=str(ROOT/'.venv/bin/luda'));args=parser.parse_args()
asyncio.run(main())
