"""Actual installed launcher/MCP inside a route-free Linux network namespace."""
import argparse
import asyncio
import base64
import errno
import hashlib
import io
import json
import os
from pathlib import Path
import pwd
import socket
import subprocess
import time
from PIL import Image
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
import luda
ROOT=Path(__file__).resolve().parents[3]

def network_proof(host_namespace,host_port):
    namespace=os.readlink('/proc/self/ns/net')
    interfaces=[name for _,name in socket.if_nameindex()]
    routes=Path('/proc/net/route').read_text().splitlines()[1:]
    probes={}
    for name,family,address in [('host-loopback',socket.AF_INET,('127.0.0.1',host_port)),('external-v4',socket.AF_INET,('192.0.2.1',9)),('external-v6',socket.AF_INET6,('2001:db8::1',9))]:
        with socket.socket(family,socket.SOCK_STREAM) as connection:
            connection.settimeout(.5);probes[name]=connection.connect_ex(address)
    assert namespace!=host_namespace and interfaces==['lo'] and not routes
    assert probes['host-loopback'] in (errno.ENETUNREACH,errno.ECONNREFUSED),probes
    assert probes['external-v4']==errno.ENETUNREACH,probes
    assert probes['external-v6'] in (errno.ENETUNREACH,errno.EADDRNOTAVAIL),probes
    return {'namespace_differs_from_host':True,'interfaces':interfaces,'ipv4_routes':routes,'canary_errno':probes,'boundary':'private kernel network namespace; loopback remains down; no external interfaces/routes; Unix sockets remain available'}

async def main(args):
    assert os.getuid()!=0 and os.environ.get('LUDA_ISOLATED_TEST_DISPLAY')=='1'
    output=args.output;release=args.release.resolve();package=Path(luda.__file__).parent.resolve()
    assert package.is_relative_to(release/'.venv')
    manifest=json.loads((release/'release.json').read_text());relative=package.relative_to(release)
    modules={str(p.relative_to(release)):hashlib.sha256(p.read_bytes()).hexdigest() for p in package.rglob('*.py')}
    expected={name:value['sha256'] for name,value in manifest['files'].items() if name.startswith(str(relative)+'/') and name.endswith('.py')}
    assert modules==expected,'Installed runtime differs from release manifest'
    (output/'runtime.json').write_text(json.dumps({'release':release.name,'module_count':len(modules),'modules':modules,'manifest_sha256':hashlib.sha256((release/'release.json').read_bytes()).hexdigest()},indent=2)+'\n')
    proof=network_proof(args.host_namespace,args.host_port);(output/'network.json').write_text(json.dumps(proof,indent=2)+'\n')
    xfce=subprocess.Popen(['xfce4-session','--disable-tcp'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);fixture=None;rows=[];trace=[]
    try:
        deadline=time.monotonic()+5
        while subprocess.run(['wmctrl','-m'],capture_output=True).returncode:
            assert time.monotonic()<deadline;await asyncio.sleep(.04)
        fixture=subprocess.Popen(['/usr/bin/python3',str(ROOT/'tests/fixture.py'),str(output)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        params=StdioServerParameters(command=str(release/'.venv/bin/luda-session'),args=['--user',pwd.getpwuid(os.getuid()).pw_name,'--session-pid',str(xfce.pid),'--',str(release/'.venv/bin/luda')],env=dict(os.environ))
        async with stdio_client(params) as streams:
            async with ClientSession(*streams) as session:
                initialized=await session.initialize();tools=await session.list_tools();rows.append('initialize-and-tools')
                async def call(name,**arguments):
                    started=time.monotonic();result=await session.call_tool(name,arguments);value=json.loads(result.content[0].text)
                    trace.append({'tool':name,'is_error':result.isError,'effect':value.get('effect'),'operation_id':value.get('operation_id'),'seconds':round(time.monotonic()-started,3)})
                    assert not result.isError,(name,value)
                    return value,result
                doctor,_=await call('desktop_doctor');assert doctor['ready'];rows.append('actual-doctor-ready')
                deadline=time.monotonic()+5
                while True:
                    windows,_=await call('desktop_windows');owned=[w for w in windows['windows'] if w['pid']==fixture.pid]
                    if owned:break
                    assert time.monotonic()<deadline;await asyncio.sleep(.03)
                wid=owned[0]['window_id'];await call('desktop_activate',window_id=wid)
                tree,_=await call('desktop_inspect',window_id=wid);field=next(n for n in tree['nodes'] if n['name']=='Contract text')
                text='Offline 日本語 😀\n\tsecond line\n'
                result,_=await call('desktop_type',element_id=field['element_id'],text=text,mode='replace');assert result['effect']=='verified'
                deadline=time.monotonic()+2
                while not (output/'state.json').exists() or json.loads((output/'state.json').read_text())['text']!=text:
                    assert time.monotonic()<deadline;await asyncio.sleep(.03)
                rows.append('native-exact-independent-text')
                button=next(n for n in tree['nodes'] if n['name']=='Record action');await call('desktop_invoke',element_id=button['element_id'])
                deadline=time.monotonic()+2
                while json.loads((output/'state.json').read_text())['clicks']!=1:
                    assert time.monotonic()<deadline;await asyncio.sleep(.03)
                rows.append('native-independent-action')
                shot,response=await call('desktop_observe',max_width=800);raw=base64.b64decode(next(c.data for c in response.content if c.type=='image'))
                with Image.open(io.BytesIO(raw)) as image:assert image.size==(shot['image_size']['width'],shot['image_size']['height'])
                (output/'screen.png').write_bytes(raw);rows.append('screenshot-valid')
                (output/'doctor.json').write_text(json.dumps(doctor,indent=2)+'\n')
                (output/'tools.json').write_text(json.dumps([tool.model_dump(mode='json') for tool in tools.tools],indent=2)+'\n')
        assert network_proof(args.host_namespace,args.host_port)==proof
        (output/'result.json').write_text(json.dumps({'passed':True,'uid':os.getuid(),'release':release.name,'mcp_version':initialized.serverInfo.version,'checks':rows,'network_boundary_preserved':True,'credential_environment':'fresh allowlist; no model/vendor credentials copied','scope':'installed ordinary launcher/MCP and native GUI; no cloud agent, downloads, or optional browser launch qualified'},indent=2)+'\n')
    finally:
        (output/'operations.json').write_text(json.dumps(trace,indent=2)+'\n')
        if fixture:fixture.terminate();fixture.wait(timeout=3)
        xfce.terminate();xfce.wait(timeout=3)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--release',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--host-namespace',required=True);p.add_argument('--host-port',type=int,required=True)
    asyncio.run(main(p.parse_args()))
