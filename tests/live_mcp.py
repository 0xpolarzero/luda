"""Protocol-level integration against an independent GTK fixture, with real stdio MCP."""
import asyncio
import argparse
import base64
import io
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
    await s.initialize()
    tools=(await s.list_tools()).tools
    (OUT/'tools.json').write_text(json.dumps([t.model_dump() for t in tools],indent=2))
    record('mcp-discovery',{'desktop_set_text','desktop_enter_text','desktop_press_keys','desktop_observe'} <= {t.name for t in tools})
    async def call(name,**args):
     r=await s.call_tool(name,args)
     assert not r.isError,(name,r)
     return json.loads(r.content[0].text),r
    d,_=await call('desktop_doctor');record('mcp-doctor',d['ready'])
    ws,_=await call('desktop_windows');w=next(w for w in ws['windows'] if w['pid']==p.pid);wid=w['window_id']
    await call('desktop_activate',window_id=wid)
    tree,_=await call('desktop_inspect',window_id=wid)
    n=next(n for n in tree['nodes'] if n['name']=='Contract text');eid=n['element_id']
    payload='MCP literal text\n日本語 👩🏽\u200d💻\n\tindent\n\n'
    value,_=await call('desktop_set_text',element_id=eid,text=payload)
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
    # Separate insertion from replacement through actual MCP calls.
    await call('desktop_set_text',element_id=eid,text='')
    await call('desktop_focus_element',element_id=eid)
    value,_=await call('desktop_enter_text',window_id=wid,text=payload,shortcut='ctrl_v')
    await asyncio.sleep(.15)
    record('mcp-paste-independent-readback',json.loads((OUT/'state.json').read_text())['text']==payload and value['effect']=='dispatched')
 finally:
  p.terminate();p.wait(timeout=3)
  (OUT/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
  print(json.dumps(results,ensure_ascii=False))

parser=argparse.ArgumentParser();parser.add_argument('--server',default=str(ROOT/'.venv/bin/silo-desktop'));args=parser.parse_args()
asyncio.run(main())
