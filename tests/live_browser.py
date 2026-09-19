"""Offline Chromium qualification: actual MCP input, independent DOM/file oracles."""
import argparse
import base64
import asyncio
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import time

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from playwright.async_api import async_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts/browser'


async def main(executable):
    OUT.mkdir(parents=True, exist_ok=True)
    records = []
    environment = {'architecture': platform.machine(), 'browser_executable': executable,
                   'uid':os.getuid(), 'accessibility_enabled':'1',
                   'revision':subprocess.run(['git','rev-parse','HEAD'],cwd=ROOT,capture_output=True,text=True).stdout.strip()}
    def record(case, passed, **details):
        records.append({'case': case, 'passed': bool(passed), **details})
        print(json.dumps(records[-1], ensure_ascii=False), flush=True)
    async def wait_value(probe, expected, timeout=3):
        deadline = time.monotonic() + timeout
        while True:
            actual = await probe()
            if actual == expected or time.monotonic() > deadline:
                return actual
            await asyncio.sleep(.03)
    try:
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(executable_path=executable, headless=False, env=dict(os.environ, ACCESSIBILITY_ENABLED="1"),
                args=['--no-sandbox', '--force-renderer-accessibility', '--host-resolver-rules=MAP * 0.0.0.0', '--window-size=1100,900'])
            environment['browser_version'] = browser.version
            try:
                page = await browser.new_page(viewport={'width':1000,'height':780})
                await page.goto((ROOT / 'tests/fixtures/browser.html').as_uri())
                async with stdio_client(StdioServerParameters(command=str(ROOT / '.venv/bin/luda'), env=dict(os.environ))) as streams:
                    async with ClientSession(*streams) as session:
                        await session.initialize()
                        async def call(name, **args):
                            response = await session.call_tool(name, args)
                            value = json.loads(response.content[0].text)
                            if response.isError:
                                raise RuntimeError(json.dumps({'tool':name, 'response':value}))
                            return value
                        async def windows():
                            return (await call('desktop_windows'))['windows']
                        async def find_window(title):
                            deadline = time.monotonic()+5
                            while True:
                                found = [w for w in await windows() if title in w['title']]
                                if len(found) == 1:
                                    return found[0]
                                if time.monotonic()>deadline:
                                    raise AssertionError(('Window not unique', title, found))
                                await asyncio.sleep(.05)
                        window = await find_window('Luda Offline Browser Qualification')
                        wid = window['window_id']
                        await call('desktop_activate',window_id=wid)
                        async def inspect(window_id=wid):
                            return await call('desktop_inspect',window_id=window_id,limit=500)
                        async def element(name,window_id=wid):
                            tree = await inspect(window_id)
                            nodes = [n for n in tree['nodes'] if n['name']==name and 'showing' in n['states']]
                            # Labels can share names; prefer the actual editable/text field.
                            fields = [n for n in nodes if n['role'] in ('entry','text','password text')]
                            if len(fields)==1:
                                return fields[0]
                            if len(nodes)==1:
                                return nodes[0]
                            raise AssertionError(('Element not unique', name, nodes))
                        tree=await inspect()
                        (OUT/'initial-tree.json').write_text(json.dumps(tree,indent=2))
                        for name,selector in [('Contract textarea','#textarea'),('Contract rich editor','#editable')]:
                            node=await element(name)
                            payload='alpha\n\t日本語 👩🏽\u200d💻 e\u0301\n\n'
                            response=await session.call_tool('desktop_type',{'element_id':node['element_id'],'text':payload,'mode':'replace'})
                            value=json.loads(response.content[0].text)
                            probe = (lambda: page.locator(selector).input_value()) if selector=='#textarea' else (lambda: page.locator(selector).inner_text())
                            actual=await probe() if response.isError else await wait_value(probe,payload)
                            record('semantic-replace-'+selector[1:],not response.isError and actual==payload,response=value,actual=actual)
                            await call('desktop_focus_element',element_id=node['element_id'])
                            await call('desktop_press_keys',window_id=wid,chord='ctrl+a')
                            await call('desktop_paste',window_id=wid,text=payload)
                            actual=await wait_value(probe,payload)
                            record('clipboard-replace-'+selector[1:],actual==payload,actual=actual)
                            # DOM is setup only for the caret test; MCP selects and inserts.
                            initial='A👩🏽\u200d💻B e\u0301C'
                            await page.locator(selector).evaluate('(e,v)=>{if(e.tagName==="TEXTAREA")e.value=v;else e.textContent=v}',initial)
                            node=await element(name)
                            await call('desktop_focus_element',element_id=node['element_id'])
                            selected=await session.call_tool('desktop_select',{'element_id':node['element_id'],'start_offset':1,'end_offset':5})
                            if selected.isError:
                                record('unicode-selection-'+selector[1:],False,response=json.loads(selected.content[0].text))
                            else:
                                typed=await session.call_tool('desktop_type',{'element_id':node['element_id'],'text':'日本語','mode':'insert'})
                                expected='A日本語B e\u0301C'
                                actual=await probe() if typed.isError else await wait_value(probe,expected)
                                record('unicode-selection-'+selector[1:],not typed.isError and actual==expected,response=json.loads(typed.content[0].text),actual=actual)
                                if typed.isError:
                                    await call('desktop_paste',window_id=wid,text='日本語')
                                    actual=await wait_value(probe,expected)
                                    record('unicode-selection-clipboard-'+selector[1:],actual==expected,actual=actual)

                        for name,selector in [('Contract read only','#readonly'),('Contract disabled','#disabled')]:
                            node=await element(name)
                            response=await session.call_tool('desktop_type',{'element_id':node['element_id'],'text':'must not write','mode':'replace'})
                            actual=await page.locator(selector).input_value()
                            record('reject-'+selector[1:],response.isError and actual=='must stay unchanged',response=json.loads(response.content[0].text))
                        # Playwright observes dialogs but deliberately does not accept them.
                        dialogs=[]
                        page.on('dialog',lambda dialog:dialogs.append(dialog))
                        for label,key,expected in [('Show synthetic alert','Return','alert closed'),('Show synthetic confirm','Escape','cancelled')]:
                            node=await element(label)
                            await call('desktop_invoke',element_id=node['element_id'],action='press')
                            deadline=time.monotonic()+3
                            while not dialogs and time.monotonic()<deadline:
                                await asyncio.sleep(.03)
                            record('dialog-observed-'+expected,bool(dialogs))
                            # Native key closes the JS modal, not Playwright's dialog API.
                            active=next(w for w in await windows() if w['active'])
                            await call('desktop_press_keys',window_id=active['window_id'],chord=key)
                            actual=await wait_value(lambda:page.locator('#dialog-result').text_content(),expected)
                            record('dialog-result-'+expected,actual==expected)
                            dialogs.clear()
                        await page.locator('#upload').evaluate('(e)=>{window.uploadEvents=[];e.addEventListener("change",()=>window.uploadEvents.push("change"));e.addEventListener("cancel",()=>window.uploadEvents.push("cancel"))}')
                        upload=OUT/'upload 日本語.txt'
                        upload.write_text('synthetic upload payload\n')
                        tree=await inspect()
                        upload_node=next(n for n in tree['nodes'] if n['role']=='push button' and n['name'].startswith('Upload synthetic file:'))
                        await call('desktop_invoke',element_id=upload_node['element_id'],action='press')
                        deadline=time.monotonic()+4
                        chooser=None
                        while time.monotonic()<deadline:
                            candidates=[w for w in await windows() if w['active'] and w['window_id']!=wid]
                            if len(candidates)==1:
                                chooser=candidates[0];break
                            await asyncio.sleep(.04)
                        record('native-file-chooser-observed',chooser is not None)
                        if chooser:
                            await call('desktop_press_keys',window_id=chooser['window_id'],chord='ctrl+l')
                            await call('desktop_paste',window_id=chooser['window_id'],text=str(upload),shortcut='ctrl_v')
                            chooser_response=await session.call_tool('desktop_inspect',{'window_id':chooser['window_id'],'limit':500})
                            chooser_tree=json.loads(chooser_response.content[0].text)
                            (OUT/'chooser-tree.json').write_text(json.dumps(chooser_tree,indent=2))
                            shot=await session.call_tool('desktop_observe',{})
                            for content in shot.content:
                                if content.type=='image':(OUT/'chooser.png').write_bytes(base64.b64decode(content.data))
                            metadata=json.loads(shot.content[0].text)
                            bounds=next(w['bounds'] for w in metadata['windows'] if w['window_id']==chooser['window_id'])
                            # Open button location in this pinned native chooser fixture;
                            # screenshot is retained so this coordinate assumption is auditable.
                            x=(bounds['x']+bounds['width']-54)*metadata['image_size']['width']/metadata['desktop_size']['width']
                            y=(bounds['y']+bounds['height']-27)*metadata['image_size']['height']/metadata['desktop_size']['height']
                            await call('desktop_click',window_id=chooser['window_id'],snapshot_id=metadata['snapshot_id'],x=x,y=y)
                            await call('desktop_wait',condition='window_absent',window_id=chooser['window_id'],timeout=4)
                            actual=await wait_value(lambda:page.locator('#upload').evaluate('(e)=>e.files[0]?.name || ""'),upload.name)
                            content=await page.locator('#upload').evaluate('async(e)=>e.files[0] ? await e.files[0].text() : ""')
                            record('native-file-upload-exact',actual==upload.name and content==upload.read_text(),filename=actual,events=await page.evaluate('window.uploadEvents'),windows=await windows())
                        second_context=await browser.new_context(viewport={'width':800,'height':600})
                        try:
                            second=await second_context.new_page()
                            await second.set_content('<title>Luda Second Browser Window</title><textarea aria-label="Second window text"></textarea>')
                            second_window=await find_window('Luda Second Browser Window')
                            await call('desktop_activate',window_id=wid)
                            rejected=await session.call_tool('desktop_paste',{'window_id':second_window['window_id'],'text':'wrong window'})
                            value=json.loads(rejected.content[0].text)
                            record('inactive-browser-window-refused',rejected.isError and value.get('code')=='FOCUS_CHANGED' and await second.locator('textarea').input_value()=='',response=value)
                            await call('desktop_activate',window_id=second_window['window_id'])
                            node=await element('Second window text',second_window['window_id'])
                            await call('desktop_focus_element',element_id=node['element_id'])
                            await call('desktop_paste',window_id=second_window['window_id'],text='second window 日本語\n')
                            actual=await wait_value(lambda:second.locator('textarea').input_value(),'second window 日本語\n')
                            record('second-window-input-exact',actual=='second window 日本語\n')
                        finally:
                            await second_context.close()
            finally:
                await browser.close()
    finally:
        (OUT/'results.json').write_text(json.dumps({'environment':environment,'cases':records},indent=2,ensure_ascii=False)+'\n')
    return 0 if records and all(r['passed'] for r in records) else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--browser',required=True)
    sys.exit(asyncio.run(main(parser.parse_args().browser)))
