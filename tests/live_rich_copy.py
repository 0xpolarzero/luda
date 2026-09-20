"""Probe independent rich plaintext copy and exact end-caret restoration.
The copied value cannot equal a stale paste clipboard: a new sentinel owns it first.
"""
import argparse
import ctypes
import json
import os
from pathlib import Path
import subprocess
import time
import uuid
from playwright.sync_api import sync_playwright
from luda.desktop import Desktop
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts/rich-copy';OUT.mkdir(parents=True,exist_ok=True)
p=argparse.ArgumentParser();p.add_argument('--executable',default='/workspace/silo-desktop-research/browsers/chromium-1243/chrome-linux-arm64/chrome');args=p.parse_args()
x=ctypes.CDLL('libX11.so.6');x.XOpenDisplay.argtypes=[ctypes.c_char_p];x.XOpenDisplay.restype=ctypes.c_void_p;x.XInternAtom.argtypes=[ctypes.c_void_p,ctypes.c_char_p,ctypes.c_int];x.XInternAtom.restype=ctypes.c_ulong;x.XGetSelectionOwner.argtypes=[ctypes.c_void_p,ctypes.c_ulong];x.XGetSelectionOwner.restype=ctypes.c_ulong;x.XCloseDisplay.argtypes=[ctypes.c_void_p]
def owner():
 display=x.XOpenDisplay(None)
 if not display:raise RuntimeError('No display')
 try:return x.XGetSelectionOwner(display,x.XInternAtom(display,b'CLIPBOARD',0))
 finally:x.XCloseDisplay(display)
def clipboard():return subprocess.run(['xclip','-selection','clipboard','-out'],capture_output=True,timeout=2,check=True).stdout.decode()
def check(name,okay,detail=None):
 results.append({'case':name,'passed':bool(okay),'detail':detail})
results=[];d=Desktop();sentinel_process=None
try:
 with sync_playwright() as pw:
  browser=pw.chromium.launch(executable_path=args.executable,headless=False,args=['--no-sandbox','--force-renderer-accessibility','--host-resolver-rules=MAP * 0.0.0.0'],env=dict(os.environ,ACCESSIBILITY_ENABLED='1'))
  try:
   page=browser.new_page();page.set_content('<title>Luda Rich Copy</title><div contenteditable="true" aria-label="Rich editor" role="textbox" style="min-height:200px;border:1px solid black"></div>')
   time.sleep(.4);w=next(x for x in d.list_windows() if 'Luda Rich Copy' in x['title']);d.activate(w['window_id'])
   page.evaluate('window.probeEvents=[];document.addEventListener("keydown",e=>probeEvents.push({key:e.key,ctrl:e.ctrlKey}));document.addEventListener("paste",e=>probeEvents.push({paste:e.clipboardData.getData("text/plain")}))')
   samples=['plain 日本語 👩🏽\u200d💻','alpha\nbeta','alpha\n\t日本語 👩🏽\u200d💻 e\u0301\n\n','  leading\n\ntrailing  \n','one\n\n\n','']
   for i,payload in enumerate(samples):
    page.set_content('<title>Luda Rich Copy</title><div contenteditable="true" aria-label="Rich editor" role="textbox" style="min-height:200px;border:1px solid black"></div>')
    page.evaluate('window.probeEvents=[];document.addEventListener("keydown",e=>probeEvents.push({key:e.key,ctrl:e.ctrlKey}));document.addEventListener("paste",e=>probeEvents.push({paste:e.clipboardData.getData("text/plain")}))')
    page.locator('div[contenteditable]').evaluate('(e)=>e.focus()')
    tree=d.inspect(w['window_id'],500);e=next(n for n in tree['nodes'] if n['name']=='Rich editor' and n['role'] in ('text','entry'))
    focus=d.element(e['element_id'],'focus');check('focus-'+str(i),focus.get('focused'),focus)
    d.paste(w['window_id'],payload,'ctrl_v')
    deadline=time.monotonic()+2
    while page.locator('div[contenteditable]').inner_text()!=payload and time.monotonic()<deadline:time.sleep(.03)
    dom=page.locator('div[contenteditable]').inner_text();check('paste-'+str(i),dom==payload,{'dom':dom,'events':page.evaluate('probeEvents'),'active':page.evaluate('document.activeElement.outerHTML'),'xfocus':subprocess.run(['xdotool','getwindowfocus'],capture_output=True,text=True).stdout,'wid':w})
    tree=d.inspect(w['window_id'],500);e=next(n for n in tree['nodes'] if n['name']=='Rich editor' and n['role'] in ('text','entry'))
    before=d.element(e['element_id'],'read');n=before['characters']
    selected=d.element(e['element_id'],'select',start_offset=0,end_offset=n)
    check('select-all-'+str(i),selected['exact_match'],selected)
    if not payload:continue  # Empty selection cannot produce a clipboard transition.
    sentinel='luda-copy-sentinel-'+uuid.uuid4().hex
    sentinel_process=subprocess.Popen(['xclip','-selection','clipboard','-in','-quiet'],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    sentinel_process.stdin.write(sentinel.encode());sentinel_process.stdin.close()
    deadline=time.monotonic()+2
    while time.monotonic()<deadline:
     try:
      if clipboard()==sentinel:break
     except Exception:pass
     time.sleep(.02)
    sentinel_owner=owner();check('sentinel-installed-'+str(i),sentinel_owner!=0 and clipboard()==sentinel)
    d.key(w['window_id'],'ctrl+c')
    deadline=time.monotonic()+2
    while owner()==sentinel_owner and time.monotonic()<deadline:time.sleep(.02)
    copied=clipboard();new_owner=owner()
    check('independent-copy-'+str(i),new_owner!=0 and new_owner!=sentinel_owner and copied==payload,{'copied':copied,'owner_changed':new_owner!=sentinel_owner})
    d.key(w['window_id'],'ctrl+a')
    # Reinstall a distinct owner before a second copy via native select-all.
    if sentinel_process.poll() is None:sentinel_process.terminate();sentinel_process.wait(timeout=2)
    sentinel_process=subprocess.Popen(['xclip','-selection','clipboard','-in','-quiet'],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    sentinel_process.stdin.write(sentinel.encode());sentinel_process.stdin.close()
    deadline=time.monotonic()+2
    while clipboard()!=sentinel and time.monotonic()<deadline:time.sleep(.02)
    sentinel_owner=owner();d.key(w['window_id'],'ctrl+c')
    deadline=time.monotonic()+2
    while owner()==sentinel_owner and time.monotonic()<deadline:time.sleep(.02)
    copied_keyboard=clipboard()
    check('native-select-all-copy-'+str(i),owner()!=sentinel_owner and copied_keyboard==payload,{'copied':copied_keyboard,'dom_selection':page.evaluate('getSelection().toString()')})
    restored=d.element(e['element_id'],'select',start_offset=n,end_offset=n)
    check('restore-end-'+str(i),restored['exact_match'],restored)
    d.paste(w['window_id'],'TAIL','ctrl_v');time.sleep(.15)
    dom=page.locator('div[contenteditable]').inner_text();check('caret-independent-dom-'+str(i),dom==payload+'TAIL',{'dom':dom})
    if sentinel_process.poll() is None:sentinel_process.terminate();sentinel_process.wait(timeout=2)
    sentinel_process=None
  finally:browser.close()
finally:
 if sentinel_process and sentinel_process.poll() is None:sentinel_process.terminate();sentinel_process.wait(timeout=2)
 d.close();(OUT/'results.json').write_text(json.dumps(results,indent=2,ensure_ascii=False));print(json.dumps({'cases':len(results),'passed':sum(x['passed'] for x in results)}))

raise SystemExit(1 if any(not r["passed"] for r in results) else 0)
