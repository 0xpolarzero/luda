import asyncio,json,os,pwd,subprocess,tempfile,time,sys
from pathlib import Path
ROOT=Path('/workspace/luda-agent-owned-secret');sys.path.insert(0,str(ROOT/'scripts'))
from agent_secret_eval import grade,SECRET
from agent_eval import stop
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
async def run():
 account=pwd.getpwnam('silo-desktop')
 with tempfile.TemporaryDirectory(prefix='secret-agent-preflight-') as d:
  b=Path(d);b.chmod(0o700);os.chown(b,account.pw_uid,account.pw_gid)
  with open('/workspace/luda-agent-secret-preflight-desktop.log','wb') as log:
   p=subprocess.Popen(['runuser','-u','silo-desktop','--',str(ROOT/'.venv/bin/python'),str(ROOT/'scripts/agent_secret_eval.py'),'--launch',d],stdout=log,stderr=log,start_new_session=True)
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
      v=await call('desktop_open_browser',url=r['url'],lifetime='temporary_session');tree=await call('desktop_inspect',window_id=v['window_id'],name='Password');field=tree['text_fields'][0];assert field['secret_entry_supported'] and not field['supported']
      await call('desktop_type_secret',element_id=field['element_id'],text=SECRET)
      await asyncio.sleep(.5);a=json.loads((b/'oracle.json').read_text());c=json.loads((b/'clipboard.json').read_text());checks=grade(a,c);print(json.dumps(checks));assert all(checks.values())
   finally:
    (b/'stop').touch()
    try:p.wait(timeout=6)
    except subprocess.TimeoutExpired:pass
    stop(p)
asyncio.run(run())
