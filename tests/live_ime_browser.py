"""Real GTK IM-context key composition through Chromium, independent DOM events."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
from playwright.sync_api import sync_playwright
from luda.desktop import Desktop
from luda.common import DesktopError
from live_ime import stop
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts/ime-browser';OUT.mkdir(parents=True,exist_ok=True)

def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--executable',required=True);args=parser.parse_args()
    if os.environ.get('LUDA_ISOLATED_TEST_DISPLAY')!='1':raise SystemExit('Private display only.')
    records=[]
    with tempfile.TemporaryDirectory(prefix='luda-browser-ime-') as temp:
        os.environ.update(XDG_CONFIG_HOME=temp+'/config',XDG_CACHE_HOME=temp+'/cache',XDG_RUNTIME_DIR=temp,GTK_IM_MODULE='gtk-im-context-simple',NO_AT_BRIDGE='0')
        wm=subprocess.Popen(['xfwm4','--compositor=off'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,start_new_session=True)
        try:
            deadline=time.monotonic()+8
            while subprocess.run(['wmctrl','-m'],capture_output=True).returncode:
                if time.monotonic()>deadline:raise RuntimeError('WM timeout')
                time.sleep(.1)
            d=Desktop()
            try:
                with sync_playwright() as pw:
                    browser=pw.chromium.launch(executable_path=args.executable,headless=False,args=['--no-sandbox','--force-renderer-accessibility','--host-resolver-rules=MAP * 0.0.0.0'],env=dict(os.environ,ACCESSIBILITY_ENABLED='1'))
                    try:
                        for operation in ('observe','focus','replace','insert','select','paste'):
                            page=browser.new_page()
                            page.set_content('''<title>Luda IME Browser</title><textarea aria-label="Composition field" style="width:500px;height:200px">BASE</textarea><script>
                            window.ime={active:false,events:[]};for(const type of ['compositionstart','compositionupdate','compositionend','beforeinput','input'])document.querySelector('textarea').addEventListener(type,e=>{if(type==='compositionstart')ime.active=true;if(type==='compositionend')ime.active=false;ime.events.push({type:e.type,data:e.data,isComposing:e.isComposing});});
                            </script>''')
                            time.sleep(.3);w=next(w for w in d.list_windows() if 'Luda IME Browser' in w['title']);wid=w['window_id'];d.activate(wid)
                            deadline=time.monotonic()+6
                            while True:
                                tree=d.inspect(wid,500)
                                field=next((n for n in tree['nodes'] if n['name']=='Composition field' and n['role'] in ('text','entry')),None)
                                if field:break
                                if time.monotonic()>deadline:
                                    (OUT/'missing-tree.json').write_text(json.dumps(tree));raise RuntimeError('field not accessible')
                                time.sleep(.1)
                            eid=field['element_id'];d.element(eid,'focus');d.key(wid,'End')
                            def oracle():return page.evaluate('({...ime,text:document.querySelector("textarea").value})')
                            before=d.element(eid,'read');d.key(wid,'ctrl+shift+u')
                            for digit in ('3','0','6','b'):d.key(wid,digit)
                            time.sleep(.1);pre=oracle();ax=d.element(eid,'read')
                            response=None
                            try:
                                if operation=='observe':response=d.element(eid,'read')
                                elif operation=='focus':response=d.element(eid,'focus')
                                elif operation=='replace':response=d.type_text(eid,'AGENT',mode='replace')
                                elif operation=='insert':response=d.type_text(eid,'AGENT',mode='insert')
                                elif operation=='select':response=d.element(eid,'select',start_offset=0,end_offset=4)
                                else:response=d.paste(wid,'AGENT')
                            except DesktopError as exc:response={'error':exc.code,'effect':exc.effect}
                            time.sleep(.1);after=oracle();d.key(wid,'Return');time.sleep(.1);completed=oracle()
                            records.append({'operation':operation,'before':before,'during_ax':ax,'pre':pre,'response':response,'after':after,'completed':completed})
                            page.close()
                    finally:browser.close()
            finally:d.close()
        finally:stop(wm)
    (OUT/'results.json').write_text(json.dumps(records,ensure_ascii=False,indent=2))
    print(json.dumps([{'op':r['operation'],'pre_active':r['pre']['active'],'post_active':r['after']['active'],'pre_text':r['pre']['text'],'post_text':r['after']['text'],'response':r['response']} for r in records],ensure_ascii=False))
    return 0 if all(r['pre']['active'] and (r['operation']=='observe' or r['response'].get('error')=='IME_COMPOSITION_ACTIVE') for r in records) else 1
if __name__=='__main__':raise SystemExit(main())
