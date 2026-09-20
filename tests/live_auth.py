"""Synthetic auth boundaries: MCP drives UI; read-only DOM is an independent oracle."""
import argparse
import base64
import ctypes
import hashlib
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
from urllib.parse import urlsplit
from auth_report import report
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from playwright.async_api import async_playwright

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/auth'


def clipboard_owner():
    # Independent Xlib oracle; do not use the production clipboard helper.
    x=ctypes.CDLL('libX11.so.6')
    x.XOpenDisplay.argtypes=[ctypes.c_char_p];x.XOpenDisplay.restype=ctypes.c_void_p
    x.XInternAtom.argtypes=[ctypes.c_void_p,ctypes.c_char_p,ctypes.c_int];x.XInternAtom.restype=ctypes.c_ulong
    x.XGetSelectionOwner.argtypes=[ctypes.c_void_p,ctypes.c_ulong];x.XGetSelectionOwner.restype=ctypes.c_ulong
    x.XCloseDisplay.argtypes=[ctypes.c_void_p]
    display=x.XOpenDisplay(None)
    if not display:raise RuntimeError('Clipboard oracle display unavailable')
    try:return x.XGetSelectionOwner(display,x.XInternAtom(display,b'CLIPBOARD',0))
    finally:x.XCloseDisplay(display)

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
            popup_clipboard_owner=None
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
                        # The alternate route uses only observed focus + public key tools.
                        # This independent owner is installed before either OTP is typed.
                        sentinel=b'luda-auth-independent-clipboard-sentinel'
                        owner=subprocess.Popen(['xclip','-selection','clipboard','-in','-quiet'],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                        try:
                            owner.stdin.write(sentinel);owner.stdin.close()
                            deadline=time.monotonic()+2
                            while subprocess.run(['xclip','-selection','clipboard','-o'],capture_output=True,timeout=2).stdout!=sentinel:
                                if time.monotonic()>deadline:raise RuntimeError('Clipboard sentinel readiness')
                                await asyncio.sleep(.02)
                            original_owner=clipboard_owner()
                            for layout in ('us','fr'):
                                # Private-display fixture setup, never a production tool action.
                                subprocess.run(['setxkbmap',layout],check=True,capture_output=True,timeout=3)
                                await click('Reset synthetic fixture')
                                await asyncio.sleep(.1)
                                field=await node('One-time code')
                                outputs=[await call('desktop_focus_element',element_id=field['element_id'])]
                                for chord in ('ctrl+a','BackSpace',*'001204'):
                                    outputs.append(await call('desktop_press_keys',window_id=wid,chord=chord))
                                digest=await page.locator('#otp').evaluate("async e => Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',new TextEncoder().encode(e.value)))).map(x=>x.toString(16).padStart(2,'0')).join('')")
                                exact=digest==hashlib.sha256(b'001204').hexdigest()
                                untouched=owner.poll() is None and clipboard_owner()==original_owner and subprocess.run(['xclip','-selection','clipboard','-o'],capture_output=True,timeout=3).stdout==sentinel
                                unsubmitted=await page.evaluate('audit.submissions===0 && !audit.verified')
                                no_echo=all('001204' not in json.dumps(response) for response in outputs)
                                record('digit-key-otp-'+layout,exact and untouched and unsubmitted and no_echo,application_hash_matches=exact,clipboard_owner_and_value_unchanged=untouched,no_implicit_submit=unsubmitted,response_contains_full_value=not no_echo)
                        finally:
                            subprocess.run(['setxkbmap','us'],check=True,capture_output=True,timeout=3)
                            if owner.poll() is None:owner.terminate();owner.wait(timeout=3)
                        await click('Reset synthetic fixture')
                        await asyncio.sleep(.1)
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
                        # Separate popup observation from the preceding intentional clipboard-retention probe.
                        popup_clipboard_owner=subprocess.Popen(['xclip','-selection','clipboard','-in','-quiet'],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                        popup_clipboard_owner.stdin.write(b'luda-popup-test-sentinel');popup_clipboard_owner.stdin.close()
                        await asyncio.sleep(.05)
                        app_context=await call('desktop_inspect',window_id=wid,limit=500)
                        expected_session='Synthetic session: luda-session-a'
                        app_session_visible=any(n['name']==expected_session for n in app_context['nodes'])
                        await click('Open local authorization window')
                        popupid=await window('Luda Local Authorization')
                        await call('desktop_activate',window_id=popupid)
                        popup_tree=await call('desktop_inspect',window_id=popupid,limit=500)
                        addresses=[n for n in popup_tree['nodes'] if n['name']=='Address and search bar' and 'Text' in n['interfaces']]
                        origin_matches=False;origin_read_code=None
                        if len(addresses)==1:
                            await call('desktop_press_keys',window_id=popupid,chord='ctrl+l')
                            err,location=await raw('desktop_read_text',element_id=addresses[0]['element_id'])
                            origin_read_code=location.get('code')
                            if not err:
                                displayed=location['text']
                                if '://' not in displayed:
                                    # Public GUI setting in this disposable browser profile only.
                                    shot=await call('desktop_observe')
                                    b=addresses[0]['bounds'];image=shot['image_size'];native=shot['desktop_size']
                                    await call('desktop_click',window_id=popupid,snapshot_id=shot['snapshot_id'],x=(b['x']+b['width']/2)*image['width']/native['width'],y=(b['y']+b['height']/2)*image['height']/native['height'],button='right')
                                    menu=await call('desktop_inspect',window_id=popupid,limit=500)
                                    visual=await session.call_tool('desktop_observe',{})
                                    for content in visual.content:
                                        if content.type=='image':(OUT/'address-context-menu.png').write_bytes(base64.b64decode(content.data))
                                    (OUT/'address-context-menu.json').write_text(visual.content[0].text)
                                    choices=[n for n in menu['nodes'] if n['name'].casefold()=='always show full urls']
                                    setting={'available':len(choices)==1,'menu_names':[n['name'] for n in menu['nodes'] if 'menu' in n['role']]}
                                    if len(choices)==1 and 'checked' not in choices[0]['states']:
                                        chosen=choices[0]
                                        action=next((a for a in chosen.get('actions',[]) if a.casefold() in ('click','press','activate','check')),None)
                                        if action:
                                            failed,outcome=await raw('desktop_invoke',element_id=chosen['element_id'],action=action)
                                            setting.update(action=action,action_error=failed,effect=outcome.get('effect'),code=outcome.get('code'))
                                    elif not choices:
                                        # Home selects the visually disabled Undo row in Chrome.
                                        # The retained screenshot then shows
                                        # Cut, Copy, Paste, Paste/search, Delete, Select all,
                                        # Manage search engines, and Always show full URLs.
                                        # Appended AI Mode makes End unstable. The selected
                                        # address and test clipboard fix the enabled rows.
                                        # This pinned visual route still requires origin readback.
                                        await call('desktop_press_keys',window_id=popupid,chord='Home')
                                        await call('desktop_press_keys',window_id=popupid,chord='Down',count=8)
                                        selected_menu=await session.call_tool('desktop_observe',{})
                                        for content in selected_menu.content:
                                            if content.type=='image':(OUT/'selected-menu-row.png').write_bytes(base64.b64decode(content.data))
                                        await call('desktop_press_keys',window_id=popupid,chord='Return')
                                        setting.update(action='Home then eight Down then Return',method='pinned_fixture_observed_menu_rows')
                                    else:
                                        await call('desktop_press_keys',window_id=popupid,chord='Escape')
                                    fresh_chrome=await call('desktop_inspect',window_id=popupid,limit=500)
                                    fresh_addresses=[n for n in fresh_chrome['nodes'] if n['name']=='Address and search bar' and 'Text' in n['interfaces']]
                                    if len(fresh_addresses)==1:
                                        err,location=await raw('desktop_read_text',element_id=fresh_addresses[0]['element_id'])
                                        if not err:displayed=location['text']
                                    setting['scheme_visible_after']='://' in displayed
                                    (OUT/'full-url-setting.json').write_text(json.dumps(setting,indent=2)+'\n')
                                parsed=urlsplit(displayed)
                                origin_matches=parsed.scheme=='http' and parsed.hostname=='127.0.0.1' and parsed.port==server.server_port
                        popup_session_visible=any(n['name']==expected_session for n in popup_tree['nodes'])
                        record('popup-origin-session-identified-before-approval',origin_matches and app_session_visible and popup_session_visible,browser_origin_matches=origin_matches,scheme_explicit=bool(len(addresses)==1 and not err and '://' in location.get('text','')),app_and_popup_session_visible=app_session_visible and popup_session_visible,address_candidates=len(addresses),read_code=origin_read_code,editable_names=[n['name'] for n in popup_tree['nodes'] if n['role']=='entry'])
                        identity_verified=origin_matches and app_session_visible and popup_session_visible
                        if identity_verified:
                            await click('Approve synthetic session',popupid)
                        else:
                            await call('desktop_window',window_id=popupid,action='close')
                        await call('desktop_wait',condition='window_absent',window_id=popupid,timeout=4)
                        await call('desktop_activate',window_id=wid)
                        record('local-popup-return-to-intended-window',identity_verified and await page.evaluate('audit.authorized'),status='observed' if identity_verified else 'blocked_by_missing_origin')
                        resumed=await call('desktop_inspect',window_id=wid,limit=500)
                        record('returned-app-session-visible',identity_verified and any(n['name']=='Synthetic local authorization complete: luda-session-a' for n in resumed['nodes']) and await page.evaluate("audit.authorizedSession==='luda-session-a'"))
                        record('oauth-origin-session-attestation',False,limitation='Window title and visible UI do not establish trusted OAuth origin/session identity; no real OAuth was exercised.')
                        await click('Require human presence')
                        human_tree=await call('desktop_inspect',window_id=wid,limit=500)
                        record('human-presence-exposed-not-completed',any('Human presence required' in n['name'] for n in human_tree['nodes']) and await page.evaluate('audit.humanRequired'))
                        await click('Reset synthetic fixture')
                        await asyncio.sleep(.2)
                        safe_old=await node('Existing session action')
                        await click('Expire synthetic session')
                        err,safe_result=await raw('desktop_invoke',element_id=safe_old['element_id'],action=next(a for a in safe_old['actions'] if a.casefold() in ('click','press','activate')))
                        safe_tree=await call('desktop_inspect',window_id=wid,limit=500)
                        record('expiry-recovery-observes-before-new-input',err and safe_result.get('code')=='STALE_TARGET' and any('Session expired' in n['name'] for n in safe_tree['nodes']) and await page.evaluate('audit.oldActions===0 && audit.unexpectedLoginActions===0 && audit.submissions===0'),stale_code=safe_result.get('code'))
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
            finally:
                if popup_clipboard_owner and popup_clipboard_owner.poll() is None:
                    popup_clipboard_owner.terminate();popup_clipboard_owner.wait(timeout=3)
                await browser.close()
    finally:
        server.shutdown();server.server_close()
        evidence=report(records)
        (OUT/'results.json').write_text(json.dumps(dict(environment=environment,**evidence),indent=2)+'\n')
    print(json.dumps({'required_workflows_passed':evidence['required_workflows_passed'],'probe_summary':evidence['probe_summary'],'failed_diagnostics':sum(not r['passed'] for r in evidence['route_diagnostics'])}),flush=True)
    return 0 if evidence['required_workflows_passed'] else 1

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--browser',required=True)
    raise SystemExit(asyncio.run(main(parser.parse_args().browser)))
