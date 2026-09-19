"""Combo option qualification; reports toolkit/provider limitations explicitly."""
import json
import os
from pathlib import Path
import subprocess
import time
from luda.desktop import Desktop
from luda.common import DesktopError
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'artifacts/combo';OUT.mkdir(parents=True,exist_ok=True)
results=[]
for kind in ('gtk','qt'):
 out=OUT/kind;out.mkdir(exist_ok=True)
 p=subprocess.Popen(['/usr/bin/python3',str(ROOT/'tests/control_fixture.py'),kind,str(out)],env=dict(os.environ,QT_ACCESSIBILITY='1',QT_LINUX_ACCESSIBILITY_ALWAYS_ON='1'))
 d=Desktop()
 try:
  for _ in range(60):
   w=next((x for x in d.list_windows() if x['pid']==p.pid),None)
   if w:break
   time.sleep(.1)
  d.activate(w['window_id']);time.sleep(.2);tree=d.inspect(w['window_id'])
  (out/'initial-tree.json').write_text(json.dumps(tree,indent=2))
  combo=next(n for n in tree['nodes'] if n['role']=='combo box')
  d.element(combo['element_id'],'invoke',action=combo['actions'][0]);time.sleep(.2)
  tree=d.inspect(w['window_id']);(out/'expanded-tree.json').write_text(json.dumps(tree,indent=2))
  options=[n for n in tree['nodes'] if n['name']=='Color blue' and n['role']!='label']
  if len(options)!=1:raise RuntimeError('Expected one visible option; found '+str(len(options)))
  r=d.element(options[0]['element_id'],'choose')
  time.sleep(.2);state=json.loads((out/'state.json').read_text())
  results.append({'toolkit':kind,'status':'supported' if r.get('effect')=='verified' and state['combo']=='Color blue' else 'failed','response':r,'actual_combo':state['combo']})
 except Exception as exc:
  results.append({'toolkit':kind,'status':'unsupported' if isinstance(exc,DesktopError) and exc.code in ('UNSUPPORTED','UNSUPPORTED_ACTION','NOT_INTERACTABLE') else 'failed','code':getattr(exc,'code',type(exc).__name__),'message':str(exc)})
 finally:
  if p.poll() is None:p.terminate();p.wait(timeout=3)
  d.close()
(OUT/'results.json').write_text(json.dumps(results,indent=2));print(json.dumps(results))
raise SystemExit(1 if any(r['status']=='failed' for r in results) else 0)
