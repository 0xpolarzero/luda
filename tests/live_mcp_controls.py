"""GTK3 protected input and selection via actual stdio MCP, hash-only oracle."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT=Path(__file__).resolve().parents[1]
PAYLOADS=('luda-synthetic-secret-ASCII-7319','luda-synthétique-🔐-日本語-7319','')

async def main():
    results=[]
    with tempfile.TemporaryDirectory(prefix='luda-mcp-controls-') as directory:
        out=Path(directory)
        fixture=subprocess.Popen(['/usr/bin/python3',str(ROOT/'tests/control_fixture.py'),'gtk',str(out)])
        async def oracle(predicate):
            deadline=time.monotonic()+3
            while time.monotonic()<deadline:
                try:
                    value=json.loads((out/'state.json').read_text())
                    if predicate(value):return value
                except (FileNotFoundError,json.JSONDecodeError):pass
                await asyncio.sleep(.04)
            raise AssertionError('Independent control oracle did not reach requested state')
        try:
            params=StdioServerParameters(command=sys.executable,args=['-m','luda.server'],env=dict(os.environ))
            async with stdio_client(params) as streams:
                async with ClientSession(*streams) as session:
                    await session.initialize()
                    tools=await session.list_tools()
                    assert {'desktop_type_secret','desktop_choose'}<={t.name for t in tools.tools}
                    async def call(name,expected_error=None,**arguments):
                        response=await session.call_tool(name,arguments)
                        serialized=response.model_dump_json()
                        assert all(not secret or secret not in serialized for secret in PAYLOADS),'Secret appeared in MCP response'
                        value=json.loads(response.content[0].text)
                        decoded=json.dumps(value,ensure_ascii=False)
                        assert all(not secret or secret not in decoded for secret in PAYLOADS),'Secret appeared in decoded MCP response'
                        if expected_error:
                            assert response.isError and value['code']==expected_error,(name,value.get('code'),expected_error)
                        else:assert not response.isError,(name,value.get('code'))
                        return value
                    for _ in range(60):
                        windows=await call('desktop_windows')
                        owner=next((w for w in windows['windows'] if w['pid']==fixture.pid),None)
                        if owner:break
                        await asyncio.sleep(.05)
                    assert owner,'fixture window missing'
                    await call('desktop_activate',window_id=owner['window_id'])
                    tree=await call('desktop_inspect',window_id=owner['window_id'])
                    nodes={}
                    for node in tree['nodes']:nodes.setdefault(node['name'],node)
                    protected=[n for n in tree['nodes'] if n.get('protected')]
                    secret=next(n for n in protected if {'sensitive','enabled'}.intersection(n['states']))
                    disabled=next(n for n in protected if not {'sensitive','enabled'}.intersection(n['states']))
                    for index,payload in enumerate(PAYLOADS):
                        result=await call('desktop_type_secret',element_id=secret['element_id'],text=payload)
                        assert result['effect']=='dispatched' and result['accepted']
                        digest=hashlib.sha256(payload.encode()).hexdigest()
                        await oracle(lambda state:state['secret_hash']==digest)
                        await call('desktop_status')
                        await call('desktop_inspect',window_id=owner['window_id'])
                        results.append('protected-hash-and-response-redaction-'+str(index))
                    await call('desktop_read_text',expected_error='PROTECTED_FIELD',element_id=secret['element_id'])
                    for mode in ('insert','replace'):
                        await call('desktop_type',expected_error='PROTECTED_FIELD',element_id=secret['element_id'],text=PAYLOADS[0],mode=mode)
                    await call('desktop_type_secret',expected_error='NOT_PROTECTED_FIELD',element_id=nodes['Control normal']['element_id'],text=PAYLOADS[0])
                    await call('desktop_type_secret',expected_error='NOT_INTERACTABLE',element_id=disabled['element_id'],text=PAYLOADS[0])
                    await call('desktop_choose',expected_error='NOT_INTERACTABLE',element_id=disabled['element_id'])
                    await oracle(lambda state:state['normal']=='' and state['secret_hash']==hashlib.sha256(b'').hexdigest())
                    results.append('protected-and-disabled-paths-refused-without-effect')
                    for name,extend,expected in [('Option one',False,['Option one']),('Option two',True,['Option one','Option two']),('Option two',True,['Option one','Option two']),('Option three',False,['Option three']),('Option three',False,['Option three'])]:
                        result=await call('desktop_choose',element_id=nodes[name]['element_id'],extend=extend)
                        assert result['effect']=='verified'
                        await oracle(lambda state:sorted(state['selected'])==expected)
                        results.append('list-'+name+'-'+str(extend))
                    for name,expected in [('Radio two',[False,True]),('Radio two',[False,True]),('Radio one',[True,False])]:
                        result=await call('desktop_choose',element_id=nodes[name]['element_id'])
                        assert result['effect']=='verified'
                        await oracle(lambda state:state['radio']==expected)
                        results.append('radio-'+name)
                    await call('desktop_choose',expected_error='INVALID_ARGUMENT',element_id=nodes['Radio two']['element_id'],extend=True)
                    await oracle(lambda state:state['radio']==[True,False])
                    history=await call('desktop_status')
                    assert any(op['method']=='element' and op.get('effect')=='dispatched' for op in history['operations'])
                    results.append('radio-extension-refused-and-status-redacted')
            print(json.dumps({'suite':'gtk3-mcp-controls','passed':len(results),'cases':results}))
        finally:
            if fixture.poll() is None:fixture.terminate()
            fixture.wait(timeout=5)

asyncio.run(main())
