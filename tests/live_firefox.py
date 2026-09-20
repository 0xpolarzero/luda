"""Official Firefox qualification; MCP drives UI, page only publishes DOM state.

Run as ordinary user in fresh Xvfb/D-Bus with LUDA_ISOLATED_TEST_DISPLAY=1.
This suite owns xfwm4; no WebDriver, debugger, or DOM mutation driver is used.
"""
import argparse
import asyncio
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import time

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from headless_tests import stop
from qualify import source_fingerprint

HTML = '''<!doctype html><meta charset="utf-8"><title>Luda Firefox Qualification</title>
<style>body{font:24px sans-serif;margin:15px}label{display:block;margin:8px}textarea{width:700px;height:100px}</style>
<label>Firefox text<textarea aria-label="Firefox text">A👩🏽‍💻B éC</textarea></label>
<label><input type=checkbox aria-label="Firefox check">Firefox check</label>
<button aria-label="Firefox button">Firefox button</button>
<label>Firefox password<input type=password aria-label="Firefox password"></label>
<script>
let clicks=0;document.querySelector('button').onclick=()=>clicks++;
function state(){let t=document.querySelector('textarea'), p=document.querySelector('[type=password]');
return {text:t.value,start:t.selectionStart,end:t.selectionEnd,checked:document.querySelector('[type=checkbox]').checked,
clicks,password_exact:p.value==='synthetic-'+String.fromCodePoint(0x65e5,0x672c,0x8a9e),password_length:p.value.length};}
setInterval(()=>fetch('/state',{method:'POST',body:JSON.stringify(state())}),80);
</script>'''

async def main(executable):
    if os.getuid() == 0 or os.environ.get('LUDA_ISOLATED_TEST_DISPLAY') != '1':
        raise SystemExit('Requires ordinary UID and explicitly isolated Xvfb/D-Bus session')
    out=ROOT/'artifacts/firefox'; out.mkdir(parents=True,exist_ok=True)
    records=[]; observed={}; before=source_fingerprint(ROOT)
    class Handler(BaseHTTPRequestHandler):
        def log_message(self,*args): pass
        def do_GET(self):
            self.send_response(200); self.send_header('Content-Type','text/html; charset=utf-8');self.end_headers();self.wfile.write(HTML.encode())
        def do_POST(self):
            data=json.loads(self.rfile.read(min(int(self.headers['Content-Length']),65536)))
            observed.clear();observed.update(data)
            (out/'oracle.json').write_text(json.dumps(data,ensure_ascii=False))
            self.send_response(204);self.end_headers()
    http=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    threading.Thread(target=http.serve_forever,daemon=True).start()
    def record(case,passed,**details):
        item={'case':case,'passed':bool(passed),**details};records.append(item);print(json.dumps(item,ensure_ascii=False),flush=True)
    async def settled(key,value):
        deadline=time.monotonic()+3
        while observed.get(key)!=value and time.monotonic()<deadline:await asyncio.sleep(.05)
        return observed.get(key)
    env=dict(os.environ,NO_AT_BRIDGE='0',ACCESSIBILITY_ENABLED='1',MOZ_ENABLE_WAYLAND='0')
    version=subprocess.run([executable,'--version'],capture_output=True,text=True,timeout=15).stdout.strip()
    wm=browser=None
    with tempfile.TemporaryDirectory(prefix='luda-firefox-xdg-') as xdg, tempfile.TemporaryDirectory(prefix='luda-firefox-profile-') as profile, (out/'browser.log').open('wb') as log:
        for key,suffix in [('XDG_CONFIG_HOME','config'),('XDG_CACHE_HOME','cache'),('XDG_DATA_HOME','data'),('XDG_RUNTIME_DIR','runtime')]:
            path=Path(xdg,suffix);path.mkdir(mode=0o700);env[key]=str(path)
        env['XDG_CONFIG_DIRS']=env['XDG_CONFIG_HOME']
        # Test-only profile: explicit a11y and no onboarding UI; proxy permits only loopback.
        prefs={'accessibility.force_disabled':-1,'termsofuse.bypassNotification':True,'browser.shell.checkDefaultBrowser':False,'browser.startup.homepage_override.mstone':'ignore','browser.aboutwelcome.enabled':False,'datareporting.policy.dataSubmissionEnabled':False,'network.proxy.type':1,'network.proxy.http':'127.0.0.1','network.proxy.http_port':9,'network.proxy.ssl':'127.0.0.1','network.proxy.ssl_port':9,'network.proxy.no_proxies_on':'localhost, 127.0.0.1','network.trr.mode':5}
        Path(profile,'user.js').write_text('\n'.join('user_pref('+json.dumps(k)+','+json.dumps(v)+');' for k,v in prefs.items()))
        try:
            wm=subprocess.Popen(['xfwm4','--compositor=off'],env=env,stdout=log,stderr=log,start_new_session=True)
            await asyncio.sleep(.5)
            browser=subprocess.Popen([executable,'--no-remote','--profile',profile,'--new-window',f'http://127.0.0.1:{http.server_port}/'],env=env,stdout=log,stderr=log,start_new_session=True)
            async with stdio_client(StdioServerParameters(command=str(ROOT/'.venv/bin/luda'),env=env)) as streams:
                async with ClientSession(*streams) as session:
                    await session.initialize()
                    async def raw(name,**args):
                        r=await session.call_tool(name,args);return not r.isError,json.loads(r.content[0].text)
                    async def call(name,**args):
                        ok,r=await raw(name,**args)
                        if not ok:raise RuntimeError(json.dumps(r))
                        return r
                    deadline=time.monotonic()+25
                    while True:
                        windows=(await call('desktop_windows'))['windows']
                        found=[w for w in windows if 'Luda Firefox Qualification' in w['title']]
                        if len(found)==1:break
                        if time.monotonic()>deadline:raise RuntimeError('Firefox fixture window unavailable')
                        await asyncio.sleep(.2)
                    wid=found[0]['window_id'];await call('desktop_activate',window_id=wid)
                    while True:
                        ok,tree=await raw('desktop_inspect',window_id=wid,limit=500)
                        if ok and any(n['name']=='Firefox text' and n['role'] in ('entry','text') for n in tree['nodes']):break
                        if time.monotonic()>deadline:
                            (out/'unavailable-tree.json').write_text(json.dumps(tree,indent=2))
                            raise RuntimeError('Firefox AX unavailable: '+json.dumps(tree))
                        await asyncio.sleep(.2)
                    (out/'tree.json').write_text(json.dumps(tree,indent=2));record('accessibility-discovery',True)
                    def node(name,roles=None):
                        nodes=[n for n in tree['nodes'] if n['name']==name and (not roles or n['role'] in roles)]
                        if len(nodes)!=1:raise RuntimeError('Ambiguous fixture node '+name)
                        return nodes[0]
                    textid=node('Firefox text',('entry','text'))['element_id']
                    ok,r=await raw('desktop_select',element_id=textid,start_offset=1,end_offset=5)
                    record('codepoint-selection',await settled('end',8)==8 and ok and observed.get('start')==1,response=r,oracle=dict(observed))
                    ok,r=await raw('desktop_type',element_id=textid,text='日本語',mode='insert')
                    record('selection-insert',await settled('text','A日本語B éC')=='A日本語B éC' and ok,response=r,oracle=dict(observed))
                    payload='alpha\n\t日本語 👩🏽\u200d💻 e\u0301\n\n'
                    ok,r=await raw('desktop_type',element_id=textid,text=payload,mode='replace')
                    record('exact-multiline-replace',await settled('text',payload)==payload and ok,response=r,oracle=dict(observed))
                    ok,r=await raw('desktop_read_text',element_id=textid)
                    record('exact-text-readback',ok and r.get('text')==observed.get('text'),response=r)
                    ok,r=await raw('desktop_type',element_id=textid,text='',mode='replace')
                    record('empty-replace',await settled('text','')=='' and ok,response=r,oracle=dict(observed))
                    check=node('Firefox check',('check box',))
                    ok,r=await raw('desktop_set_checked',element_id=check['element_id'],checked=True)
                    record('checkbox',await settled('checked',True) is True and ok,response=r)
                    button=node('Firefox button',('push button',))
                    action=button.get('actions',['click'])[0]
                    if isinstance(action,dict):action=action['name']
                    ok,r=await raw('desktop_invoke',element_id=button['element_id'],action=action)
                    record('button',await settled('clicks',1)==1 and ok,response=r)
                    tree=await call('desktop_inspect',window_id=wid,limit=500)
                    password=node('[protected]',('password text',))['element_id']
                    ok,r=await raw('desktop_read_text',element_id=password)
                    record('protected-read-refusal',not ok,response=r)
                    secret='synthetic-日本語'
                    ok,r=await raw('desktop_type',element_id=password,text=secret,mode='replace')
                    record('protected-ordinary-type-refusal',not ok and secret not in json.dumps(r),response=r)
                    ok,r=await raw('desktop_type_secret',element_id=password,text=secret)
                    record('explicit-protected-input',await settled('password_exact',True) is True and ok and secret not in json.dumps(r),response=r)
                    await call('desktop_focus_element',element_id=textid)
                    await call('desktop_press_keys',window_id=wid,chord='ctrl+a')
                    ok,r=await raw('desktop_paste',window_id=wid,text=payload)
                    actual=await settled('text',payload)
                    record('explicit-clipboard-multiline',ok and actual==payload,response=r,oracle=dict(observed))
                    for case,initial,start,end,insert,expected in [
                        ('ascii-to-astral-caret','AB',1,1,'😀','A😀B'),
                        ('genuine-feff-preserved','\ufeffA😀\ufeff\ufeffB\n',2,3,'🦊','\ufeffA🦊\ufeff\ufeffB\n'),
                    ]:
                        setup_ok,setup=await raw('desktop_type',element_id=textid,text=initial,mode='replace')
                        setup_actual=await settled('text',initial)
                        if not setup_ok or setup_actual!=initial:
                            record(case,False,stage='setup',response=setup,oracle=dict(observed));continue
                        select_ok,selected=await raw('desktop_select',element_id=textid,start_offset=start,end_offset=end)
                        if not select_ok:
                            record(case,False,stage='selection',response=selected);continue
                        ok,r=await raw('desktop_type',element_id=textid,text=insert,mode='insert')
                        actual=await settled('text',expected)
                        read_ok,read=await raw('desktop_read_text',element_id=textid)
                        record(case,ok and read_ok and actual==expected and read.get('text')==expected and read.get('caret_offset')==start+len(insert),response=r,readback=read,oracle=dict(observed))
        except Exception as exc:
            import traceback
            record('suite-completion',False,error=''.join(traceback.format_exception(exc)))
        finally:
            if browser:stop(browser)
            if wm:stop(wm)
            http.shutdown();http.server_close()
    after=source_fingerprint(ROOT)
    record('source-unchanged',before==after)
    (out/'results.json').write_text(json.dumps({'environment':{'uid':os.getuid(),'version':version,'executable':executable,'binary_sha256':hashlib.sha256(Path(executable).read_bytes()).hexdigest(),'source_before':before,'source_after':after},'records':records},indent=2,ensure_ascii=False))
    return int(not all(r['passed'] for r in records))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--executable',required=True)
    raise SystemExit(asyncio.run(main(p.parse_args().executable)))
