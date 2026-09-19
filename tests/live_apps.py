"""Independent app-level verification; all documents/content are owned offline fixtures."""
import argparse
import json
from pathlib import Path
import subprocess
import time
from playwright.sync_api import sync_playwright
from luda.desktop import Desktop

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts'/'apps';OUT.mkdir(exist_ok=True)
results=[]
d=Desktop()
def record(name,ok,detail=None):
 results.append({'case':name,'passed':bool(ok),'details':detail})
 assert ok,(name,detail)
def window(pid=None,title=None):
 for _ in range(40):
  ws=d.list_windows();matches=[w for w in ws if (pid is None or w['pid']==pid) and (title is None or title in w['title'])]
  if len(matches)==1:return matches[0]
  time.sleep(.1)
 raise AssertionError(('window not found',pid,title))

def editor():
 file=OUT/'saved exact 日本語.txt';file.write_text('initial\n')
 p=subprocess.Popen(['mousepad','--disable-server',str(file)])
 try:
  w=window(p.pid);wid=w['window_id'];d.activate(wid);time.sleep(.4)
  tree=d.inspect(wid)
  (OUT/'mousepad-tree.json').write_text(json.dumps(tree,indent=2))
  text=next(n for n in tree['nodes'] if 'EditableText' in n['interfaces'] and 'multi-line' in n['states'])
  value='Saved by Luda desktop\n\tindent\n日本語 👩🏽\u200d💻\n\n'
  d.element(text['element_id'],'set',text=value);d.element(text['element_id'],'focus');d.key(wid,'ctrl+s')
  for _ in range(30):
   if file.read_text()==value:break
   time.sleep(.1)
  record('mousepad-save-file-exact',file.read_text()==value)
  # Save As drives a native dialog and actual creation of a second file.
  newfile=OUT/'saved-as 日本語.txt'
  if newfile.exists():newfile.unlink()
  d.key(wid,'ctrl+shift+s');time.sleep(.4)
  modal=next(w for w in d.list_windows() if w['pid']==p.pid and w['active'])
  modal_tree=d.inspect(modal['window_id'])
  (OUT/'save-dialog-tree.json').write_text(json.dumps(modal_tree,indent=2))
  names=[n for n in modal_tree['nodes'] if 'EditableText' in n['interfaces'] and 'single-line' in n['states'] and 'showing' in n['states']]
  assert names,modal_tree
  field=next((n for n in names if 'name' in n['name'].lower()),names[0])
  d.element(field['element_id'],'set',text=str(newfile));d.element(field['element_id'],'focus');d.key(modal['window_id'],'Return')
  for _ in range(30):
   if newfile.exists():break
   time.sleep(.1)
  record('mousepad-save-as-dialog-exact',newfile.exists() and newfile.read_text()==value)
 finally:p.terminate();p.wait(timeout=3)

def browser(executable):
 with sync_playwright() as pw:
  b=pw.chromium.launch(executable_path=executable,headless=False,args=['--no-sandbox','--force-renderer-accessibility','--host-resolver-rules=MAP * 0.0.0.0','--window-size=1000,750'])
  try:
   page=b.new_page(viewport={'width':960,'height':640})
   page.set_content('<title>Silo Offline Browser Contract</title><textarea aria-label="Contract textarea" style="position:absolute;left:0;top:0;width:90vw;height:80vh"></textarea>')
   w=window(title='Silo Offline Browser Contract');wid=w['window_id'];d.activate(wid);time.sleep(.3)
   for i,value in enumerate(['alpha\nbeta\n','tabs\there\n','日本語 👩🏽\u200d💻 e\u0301\n\n']):
    # Setup/readback is independent; candidate supplies the real desktop input.
    page.locator('textarea').fill('');page.locator('textarea').focus()
    shot=d.observe();w=d.target_window(wid)
    px=w['bounds']['x']+180;py=w['bounds']['y']+240
    d.pointer(wid,shot['snapshot_id'],px*shot['image_size']['width']/shot['desktop_size']['width'],py*shot['image_size']['height']/shot['desktop_size']['height'])
    d.paste(wid,value,'ctrl_v')
    deadline=time.monotonic()+2
    while page.locator('textarea').input_value()!=value and time.monotonic()<deadline:time.sleep(.05)
    record('chromium-literal-paste-'+str(i),page.locator('textarea').input_value()==value)
  finally:b.close()

def terminal():
 path=OUT/'terminal-reader.json'
 p=subprocess.Popen(['xfce4-terminal','--disable-server','--title=Silo Passive Terminal Contract','--execute','/usr/bin/python3',str(ROOT/'tests/passive_terminal.py'),str(path)])
 try:
  w=window(p.pid);wid=w['window_id'];d.activate(wid);time.sleep(.3)
  value='alpha\nbeta\n日本語 ✓\ntabs\there\n'
  d.paste(wid,value,'ctrl_shift_v');time.sleep(.3)
  ws=[w for w in d.list_windows() if w['pid']==p.pid and w['active']]
  assert len(ws)==1,ws
  tree=d.inspect(ws[0]['window_id'])
  (OUT/'terminal-dialog-tree.json').write_text(json.dumps(tree,indent=2))
  buttons=[n for n in tree['nodes'] if n['role']=='push button' and 'paste' in n['name'].lower()]
  if buttons:
   record('terminal-paste-dialog-observed',True)
   # This fixture is a passive reader, so accepting paste cannot execute commands.
   button=buttons[0];d.element(button['element_id'],'invoke',action=button['actions'][0])
  deadline=time.monotonic()+2
  while time.monotonic()<deadline:
   actual=json.loads(path.read_text())['text']
   if actual==value:break
   time.sleep(.05)
  record('xfce-terminal-confirmed-paste-exact',actual==value,{'expected':value,'actual':actual})
 finally:p.terminate();p.wait(timeout=3)

p=argparse.ArgumentParser();p.add_argument('--browser',required=True);args=p.parse_args()
try:
 editor();browser(args.browser);terminal()
finally:
 d.close();(OUT/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2));print(json.dumps(results,ensure_ascii=False))
