"""Chromium code-point selection and opaque-hypertext regression, DOM oracle."""
import argparse
import json
from pathlib import Path
import os
import time
from playwright.sync_api import sync_playwright
from luda.desktop import Desktop
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts/browser-offset';OUT.mkdir(parents=True,exist_ok=True)
p=argparse.ArgumentParser();p.add_argument('--executable',default='/workspace/silo-desktop-research/browsers/chromium-1243/chrome-linux-arm64/chrome');args=p.parse_args()
results=[]
def check(case,okay,detail=None):
 results.append({'case':case,'passed':bool(okay),'detail':detail});assert okay,(case,detail)
d=Desktop()
try:
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path=args.executable,headless=False,args=['--no-sandbox','--force-renderer-accessibility','--host-resolver-rules=MAP * 0.0.0.0'],env=dict(os.environ,ACCESSIBILITY_ENABLED='1'))
  try:
   page=browser.new_page();page.set_content('<title>Luda Offset Probe</title><textarea aria-label="Offset text"></textarea><div contenteditable="true" aria-label="Rich text" role="textbox"></div>')
   time.sleep(.4);w=next(x for x in d.list_windows() if 'Luda Offset Probe' in x['title']);d.activate(w['window_id'])
   for selector,name in [('textarea','Offset text'),('div[contenteditable]','Rich text')]:
    for start,end in ((1,5),(1,8),(5,8),(2,5)):
     text='A👩🏽\u200d💻B e\u0301C'
     page.locator(selector).evaluate('(e,t)=>{if(e.tagName==="TEXTAREA")e.value=t;else e.textContent=t;e.focus()}',text)
     tree=d.inspect(w['window_id'],500);e=next(x for x in tree['nodes'] if x['name']==name and x['role'] in ('text','entry'))
     selected=d.element(e['element_id'],'select',start_offset=start,end_offset=end)
     actual=d.element(e['element_id'],'read')
     dom=page.locator(selector).evaluate('(e)=>e.tagName==="TEXTAREA"?{start:e.selectionStart,end:e.selectionEnd}:{start:getSelection().anchorOffset,end:getSelection().focusOffset}')
     expected_dom={'start':len(text[:start].encode('utf-16-le'))//2,'end':len(text[:end].encode('utf-16-le'))//2}
     check(name+'-'+str(start)+'-'+str(end),selected['exact_match'] and actual['selections']==[{'start_offset':start,'end_offset':end}] and dom==expected_dom,{'selected':selected,'read':actual,'dom':dom})
   page.locator('div[contenteditable]').evaluate('(e)=>{e.innerHTML="alpha<div>日本語 👩🏽‍💻</div><div><br></div>";e.focus()}')
   tree=d.inspect(w['window_id'],500);e=next(x for x in tree['nodes'] if x['name']=='Rich text' and x['role'] in ('text','entry'))
   actual=d.element(e['element_id'],'read');dom=page.locator('div[contenteditable]').inner_text()
   check('opaque-hypertext-explicit',actual['text_representation']=='hypertext' and not actual['plain_text_verification_supported'] and len(actual['embedded_objects'])==2 and actual['text']!=dom,{'read':actual,'dom':dom})
   page.locator('textarea').evaluate('(e)=>{e.value="literal \\uFFFC character";e.focus()}')
   tree=d.inspect(w['window_id'],500);e=next(x for x in tree['nodes'] if x['name']=='Offset text' and x['role'] in ('text','entry'))
   actual=d.element(e['element_id'],'read');check('literal-object-character-is-plain',actual['plain_text_verification_supported'] and actual['text']=='literal \ufffc character',actual)
  finally:browser.close()
finally:
 d.close();(OUT/'results.json').write_text(json.dumps(results,indent=2,ensure_ascii=False))
 print(json.dumps({'cases':len(results),'passed':sum(x['passed'] for x in results)}))
