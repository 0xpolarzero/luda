"""Protected input and observed-option selection, with independent toolkit oracles."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from luda.desktop import Desktop
from luda.common import DesktopError
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts/controls';OUT.mkdir(parents=True,exist_ok=True)
results=[]
def check(kind,name,okay,detail=None):
 results.append({'toolkit':kind,'case':name,'passed':bool(okay),'detail':detail});assert okay,(kind,name,detail)
for kind in ('gtk','qt'):
 out=OUT/kind;out.mkdir(exist_ok=True)
 p=subprocess.Popen(['/usr/bin/python3',str(ROOT/'tests/control_fixture.py'),kind,str(out)],env=dict(os.environ,QT_ACCESSIBILITY='1',QT_LINUX_ACCESSIBILITY_ALWAYS_ON='1'))
 d=Desktop()
 def state():time.sleep(.1);return json.loads((out/'state.json').read_text())
 def reject(name,code,fn):
  try:fn()
  except DesktopError as e:check(kind,name,e.code==code,e.code)
  else:check(kind,name,False)
 try:
  for _ in range(60):
   w=next((x for x in d.list_windows() if x['pid']==p.pid),None)
   if w:break
   time.sleep(.1)
  d.activate(w['window_id']);time.sleep(.2);tree=d.inspect(w['window_id']);(out/'tree.json').write_text(json.dumps(tree,indent=2))
  nodes={}
  for n in tree['nodes']:nodes.setdefault(n['name'],n)
  protected=[n for n in tree['nodes'] if n.get('protected')]
  secret=next(n for n in protected if {'sensitive','enabled'}.intersection(n['states']))
  disabled=next(n for n in protected if not {'sensitive','enabled'}.intersection(n['states']))
  for i,text in enumerate(['test-only ASCII','synthétique 🔐 日本語','']):
   r=d.element(secret['element_id'],'secret',text=text)
   check(kind,'explicit-secret-'+str(i),r['effect']=='dispatched' and r['accepted'] and state()['secret_hash']==hashlib.sha256(text.encode()).hexdigest())
   check(kind,'no-secret-response-'+str(i),text=='' or text not in json.dumps(r))
  reject('secret-nonprotected-refused','NOT_PROTECTED_FIELD',lambda:d.element(nodes['Control normal']['element_id'],'secret',text='not allowed'))
  reject('secret-disabled-refused','NOT_INTERACTABLE',lambda:d.element(disabled['element_id'],'secret',text='not allowed'))
  reject('ordinary-read-protected','PROTECTED_FIELD',lambda:d.element(secret['element_id'],'read'))
  reject('ordinary-set-protected','PROTECTED_FIELD',lambda:d.element(secret['element_id'],'set',text='not allowed'))
  for name,extend,expected in [('Option one',False,['Option one']),('Option two',True,['Option one','Option two']),('Option three',False,['Option three']),('Option three',False,['Option three'])]:
   r=d.element(nodes[name]['element_id'],'choose',extend=extend)
   check(kind,'choose-'+str(len(results)),r['effect']=='verified' and sorted(state()['selected'])==expected,r)
  r=d.element(nodes['Radio two']['element_id'],'choose');check(kind,'radio-two',r['effect']=='verified' and state()['radio']==[False,True],r)
  r=d.element(nodes['Radio two']['element_id'],'choose');check(kind,'radio-idempotent',r['effect']=='verified' and state()['radio']==[False,True],r)
 finally:
  if p.poll() is None:p.terminate();p.wait(timeout=3)
  d.close();(OUT/'results.json').write_text(json.dumps(results,indent=2))
print(json.dumps({'passed':sum(x['passed'] for x in results),'cases':len(results)}))
