"""Run as desktop user. Mutates only its own fixture, and terminates it afterward."""
import json
from pathlib import Path
import subprocess
import os
import signal
import sys
import time
from silo_desktop.desktop import Desktop
from silo_desktop.common import DesktopError

ROOT=Path(__file__).resolve().parents[1]
output=ROOT/'artifacts'/'native';output.mkdir(exist_ok=True)
p=subprocess.Popen(['/usr/bin/python3',str(ROOT/'tests'/'fixture.py'),str(output)])
d=Desktop();results=[]
def record(name,condition,details=None):
 results.append({'case':name,'passed':bool(condition),'details':details})
 assert condition,(name,details)
def state():
 time.sleep(.12)
 return json.loads((output/'state.json').read_text())
def expected_error(name,code,fn):
 try:fn()
 except DesktopError as exc:record(name,exc.code==code,exc.code)
 else:record(name,False,'did not reject')
try:
 for _ in range(40):
  windows=d.list_windows();w=next((w for w in windows if w['pid']==p.pid),None)
  if w:break
  time.sleep(.1)
 assert w
 wid=w['window_id'];d.activate(wid);time.sleep(.35)
 inspect=d.inspect(wid)
 (output/'inspect.json').write_text(json.dumps(inspect,indent=2))
 editor=next(n for n in inspect['nodes'] if n['name']=='Contract text')
 eid=editor['element_id']
 samples=['alpha\nbeta\n','ASCII _ {} [] @!\ncafé — 日本語 ✓\n','tabs\there\n','\n\n leading and trailing  \n','emoji 👩🏽\u200d💻 e\u0301 العربية עברית\n','', 'long '+('行\n'*4000)]
 for i,text in enumerate(samples):
  r=d.element(eid,'set',text=text)
  record('text-replacement-'+str(i),r['exact_match'] and state()['text']==text)
 d.element(eid,'set',text='');d.element(eid,'focus')
 for i,text in enumerate(samples[:5]):
  d.element(eid,'set',text='');d.element(eid,'focus');d.paste(wid,text,'ctrl_v')
  record('literal-paste-'+str(i),state()['text']==text)
 before=state()['text']
 expected_error('reject-NUL','UNSUPPORTED_TEXT',lambda:d.paste(wid,'a\0b','ctrl_v'))
 expected_error('reject-CRLF','UNSUPPORTED_TEXT',lambda:d.element(eid,'set',text='a\r\nb'))
 record('invalid-text-no-change',state()['text']==before)
 hidden=next(n for n in inspect['nodes'] if n['name']=='Hidden text')
 expected_error('hidden-text-refused','NOT_INTERACTABLE',lambda:d.element(hidden['element_id'],'set',text='must not write'))
 disabled=next(n for n in inspect['nodes'] if n['name']=='Disabled action')
 expected_error('disabled-action-refused','NOT_INTERACTABLE',lambda:d.element(disabled['element_id'],'invoke',action='click'))
 expected_error('surrogate-refused','UNSUPPORTED_TEXT',lambda:d.paste(wid,'\ud800','ctrl_v'))
 expected_error('oversized-text-refused','TEXT_TOO_LARGE',lambda:d.element(eid,'set',text='x'*1_000_001))
 secret=next(n for n in inspect['nodes'] if n['protected'])
 expected_error('protected-read','PROTECTED_FIELD',lambda:d.element(secret['element_id'],'read'))
 button=next(n for n in inspect['nodes'] if n['name']=='Record action')
 d.element(button['element_id'],'invoke',action=button['actions'][0]);record('semantic-button',state()['clicks']==1)
 shot=d.observe(800);b=button['bounds'];iw=shot['image_size']['width'];nw=shot['desktop_size']['width'];ih=shot['image_size']['height'];nh=shot['desktop_size']['height']
 x=(b['x']+b['width']/2)*iw/nw;y=(b['y']+b['height']/2)*ih/nh
 d.pointer(wid,shot['snapshot_id'],x,y);record('scaled-coordinate-button',state()['clicks']==2)
 expected_error('coordinate-outside-image','OUT_OF_BOUNDS',lambda:d.pointer(wid,shot['snapshot_id'],-1,y))
 d.snapshots[shot['snapshot_id']]['time']-=20
 expected_error('expired-screenshot','STALE_OBSERVATION',lambda:d.pointer(wid,shot['snapshot_id'],x,y))
 shot=d.observe();subprocess.run(['xdotool','windowmove',str(w['xid']),'100','150'],check=True);time.sleep(.1)
 expected_error('moved-window-screenshot','STALE_OBSERVATION',lambda:d.pointer(wid,shot['snapshot_id'],x,y))
 expected_error('invalid-key','INVALID_KEY',lambda:d.key(wid,'ctrl+s\nReturn'))
 other=Desktop()
 try:
  with d.transaction():expected_error('cross-server-lock','BUSY',lambda:other.transaction().__enter__())
 finally:other.close()
 # A stopped app must not permanently wedge an accessibility request.
 os.kill(p.pid,signal.SIGSTOP)
 began=time.monotonic()
 try:
  try:d.element(eid,'set',text='uncertain write')
  except DesktopError as exc:record('hung-app-bounded-refusal',time.monotonic()-began<6 and exc.effect in ('none','uncertain'),{'code':exc.code,'seconds':time.monotonic()-began})
  else:record('hung-app-bounded-refusal',False)
 finally:os.kill(p.pid,signal.SIGCONT)
 time.sleep(.2)
 fresh=d.inspect(wid);record('recover-after-hung-provider',fresh['available'])
 d.elements[eid]['time']-=70
 expected_error('expired-element','STALE_TARGET',lambda:d.element(eid,'set',text='bad'))
 p.terminate();p.wait(timeout=3)
 expected_error('closed-window','STALE_TARGET',lambda:d.activate(wid))
finally:
 if p.poll() is None:p.terminate();p.wait(timeout=3)
 d.close()
 (output/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
 print(json.dumps(results,ensure_ascii=False))
