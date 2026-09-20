"""Synthetic auth boundaries: MCP drives UI; read-only DOM is an independent oracle."""
import argparse
import asyncio
import functools
import http.server
import json
import os
from pathlib import Path
import platform
import subprocess
import threading
import time
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/auth'

async def main(executable):
    if os.getuid()==0 or os.environ.get('LUDA_ISOLATED_TEST_DISPLAY')!='1':
        raise RuntimeError('Requires ordinary UID and private qualification display.')
    OUT.mkdir(parents=True,exist_ok=True)
    records=[]
    def record(case,passed,**details):
        row=dict(case=case,passed=bool(passed),**details); records.append(row)
        print(json.dumps(row),flush=True)
    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self,*args): pass
    server=http.server.ThreadingHTTPServer(('127.0.0.1',0),functools.partial(Handler,directory=str(ROOT/'tests/fixtures')))
    threading.Thread(target=server.serve_forever,daemon=True).start()
    environment=dict(uid=os.getuid(),architecture=platform.machine(),browser_executable=executable)
    try:
        async with async_playwright() as pw:
            browser=await pw.chromium.launch(executable_path=executable,headless=False,env=dict(os.environ,ACCESSIBILITY_ENABLED='1'),args=['--no-sandbox','--force-renderer-accessibility','--disable-background-networking','--window-size=1100,900'])
            environment['browser_version']=browser.version
            context=await browser.new_context()
            await context.route('**/*',lambda route: route.continue_() if route.request.url.startswith(f'http://127.0.0.1:{server.server_port}/') else route.abort())
            page=await context.new_page()
            await page.goto(f'http://127.0.0.1:{server.server_port}/auth.html')
            try:
                async with stdio_client(StdioServerParameters(command=str(ROOT/'.venv/bin/luda'),env=dict(os.environ))) as streams:
                    async with ClientSession(*streams) as session:
                        await session.initialize()
                        async def raw(name,**args):
                            r=await session.call_tool(name,args);return r.isError,json.loads(r.content[0].text)
                        async def call(name,**args):
                            err,value=await raw(name,**args)
                            if err: raise RuntimeError(name+': '+str(value.get('code')))
                            return value
                        async def window(title):
                            until=time.monotonic()+5
                            while True:
                                found=[w for w in (await call('desktop_windows'))['windows'] if title in w['title']]
                                if len(found)==1:return found[0]['window_id']
                                if time.monotonic()>until:raise RuntimeError('Window not unique: '+title)
                                await asyncio.sleep(.05)
                        wid=await window('Luda Synthetic Authentication')
                        await call('desktop_activate',window_id=wid)
                        async def node(name,window_id=wid):
                            tree=await call('desktop_inspect',window_id=window_id,limit=500)
                            found=[n for n in tree['nodes'] if n['name']==name and n['role'] in ('entry','text','push button','password text')]
                            if len(found)!=1:raise RuntimeError('Element not unique: '+name)
                            return found[0]
                        async def click(name,window_id=wid):
                            n=await node(name,window_id);return await call('desktop_invoke',element_id=n['element_id'],action=next(a for a in n['actions'] if a.casefold() in ('click','press','activate')))
                        otp=await node('One-time code')
                        old=await node('Existing session action')
                        err,result=await raw('desktop_type_secret',element_id=otp['element_id'],text='001204')
                        record('unmasked-otp-secret-path-refused',err and result.get('code')=='NOT_PROTECTED_FIELD' and await page.locator('#otp').input_value()=='',code=result.get('code'))
                        err,result=await raw('desktop_type',element_id=otp['element_id'],text='001204',mode='replace')
                        record('ordinary-otp-leading-zeros',not err and await page.locator('#otp').input_value()=='001204' and '001204' not in json.dumps(result),interfaces=otp['interfaces'],response_contains_value='001204' in json.dumps(result))
                        clipboard=subprocess.run(['xclip','-selection','clipboard','-o'],capture_output=True,timeout=3).stdout.decode()
                        record('ordinary-otp-not-secret-storage',clipboard!='001204',clipboard_retains_value=clipboard=='001204',limitation='Unmasked ordinary typing may use CLIPBOARD and readback; no one-time-value retention guarantee.')
                        masked_tree=await call('desktop_inspect',window_id=wid,limit=500)
                        protected=[n for n in masked_tree['nodes'] if n.get('protected')]
                        if len(protected)!=1:raise RuntimeError('Protected fixture not unique')
                        err,result=await raw('desktop_type_secret',element_id=protected[0]['element_id'],text='001204')
                        record('browser-protected-otp-support',not err and await page.locator('#masked').input_value()=='001204',code=result.get('code'),response_contains_value='001204' in json.dumps(result))
                        await click('Verify synthetic code')
                        record('explicit-otp-submit-clears-fixture',await page.evaluate('audit.verified') and await page.locator('#otp').input_value()=='')
                        await click('Open local authorization window')
                        popupid=await window('Luda Local Authorization')
                        await call('desktop_activate',window_id=popupid)
                        await click('Approve synthetic session',popupid)
                        await call('desktop_wait',condition='window_absent',window_id=popupid,timeout=4)
                        await call('desktop_activate',window_id=wid)
                        record('local-popup-return-to-intended-window',await page.evaluate('audit.authorized'))
                        record('oauth-origin-session-attestation',False,limitation='Window title and visible UI do not establish trusted OAuth origin/session identity; no real OAuth was exercised.')
                        await click('Require human presence')
                        human_tree=await call('desktop_inspect',window_id=wid,limit=500)
                        record('human-presence-exposed-not-completed',any('Human presence required' in n['name'] for n in human_tree['nodes']) and await page.evaluate('audit.humanRequired'))
                        await click('Reset synthetic fixture')
                        await asyncio.sleep(.2)
                        old=await node('Existing session action')
                        observed=await call('desktop_observe')
                        # Test old screenshot coordinates after same-window content replacement.
                        b=old['bounds']; native=observed['desktop_size']; image=observed['image_size']
                        x=(b['x']+b['width']//2)*image['width']/native['width']
                        y=(b['y']+b['height']//2)*image['height']/native['height']
                        await click('Expire synthetic session')
                        coorderr,coordresult=await raw('desktop_click',window_id=wid,snapshot_id=observed['snapshot_id'],x=x,y=y)
                        record('old-screenshot-after-same-window-replacement',coorderr and await page.evaluate('audit.unexpectedLoginActions===0'),new_login_action_count=await page.evaluate('audit.unexpectedLoginActions'),code=coordresult.get('code'),limitation='Geometry/identity checks do not prove unchanged page content.')
                        login_actions_before=await page.evaluate('audit.unexpectedLoginActions')
                        err,result=await raw('desktop_invoke',element_id=old['element_id'],action=next(a for a in old['actions'] if a.casefold() in ('click','press','activate')))
                        record('expired-session-old-element-refused',err and result.get('code')=='STALE_TARGET' and await page.evaluate('audit.oldActions===0') and await page.evaluate('audit.unexpectedLoginActions')==login_actions_before,code=result.get('code'))
                        fresh=await call('desktop_inspect',window_id=wid,limit=500)
                        record('expiry-visible-in-fresh-observation',any('Session expired' in n['name'] for n in fresh['nodes']))
            finally:await browser.close()
    finally:
        server.shutdown();server.server_close()
        (OUT/'results.json').write_text(json.dumps(dict(environment=environment,cases=records),indent=2)+'\n')
    return 0 if records and all(r['passed'] for r in records) else 1

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--browser',required=True)
    raise SystemExit(asyncio.run(main(parser.parse_args().browser)))
