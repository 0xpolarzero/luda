import asyncio,json,os,pwd,subprocess,tempfile,time,sys
from pathlib import Path
ROOT=Path('/workspace/luda-agent-native-range');sys.path.insert(0,str(ROOT/'scripts'))
from agent_range_eval import grade
from agent_eval import stop
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
async def run():
 account=pwd.getpwnam('silo-desktop')
 with tempfile.TemporaryDirectory(prefix='range-agent-preflight-') as d:
  b=Path(d);b.chmod(0o700);os.chown(b,account.pw_uid,account.pw_gid)
  with open('/workspace/luda-agent-range-preflight-desktop.log','wb') as log:
   p=subprocess.Popen(['runuser','-u','silo-desktop','--',str(ROOT/'.venv/bin/python'),str(ROOT/'scripts/agent_range_eval.py'),'--launch',d],stdout=log,stderr=log,start_new_session=True)
   try:
    deadline=time.monotonic()+25
    while not (b/'ready.json').exists():
     assert p.poll() is None and time.monotonic()<deadline;await asyncio.sleep(.1)
    r=json.loads((b/'ready.json').read_text());args=['-u','silo-desktop','--','/usr/bin/env',*[k+'='+v for k,v in r['environment'].items()],str(ROOT/'.venv/bin/luda')]
    async with stdio_client(StdioServerParameters(command='/usr/sbin/runuser',args=args)) as streams:
     async with ClientSession(*streams) as s:
      await s.initialize()
      async def call(tool,**kw):
       raw=await s.call_tool(tool,kw);v=json.loads(raw.content[0].text);assert v.get('ok') is True,(tool,v);return v
      windows=await call('desktop_windows');wid=next(w['window_id'] for w in windows['windows'] if w['title']=='Range Desk');await call('desktop_activate',window_id=wid)
      initial=json.loads((b/'state.json').read_text());assert initial['selected_ids']==[6],initial
      tree=await call('desktop_inspect',window_id=wid,role='table cell');items={n['name']:n['element_id'] for n in tree['nodes']}
      await call('desktop_choose',element_id=items['Record 002'],range_end_id=items['Record 004'],extend=True)
      await asyncio.sleep(.3);actual=json.loads((b/'state.json').read_text());checks=grade(actual);print(json.dumps({'initial':initial,'actual':actual,'checks':checks}));assert all(checks.values())
   finally:
    (b/'stop').touch()
    try:p.wait(timeout=6)
    except subprocess.TimeoutExpired:pass
    stop(p)
asyncio.run(run())
