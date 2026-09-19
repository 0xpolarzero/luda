"""Qualify real Qt5 and GTK4; hold /tmp/luda-live-tests.lock for the entire run.
Unsupported providers are recorded explicitly, never counted as successful effects.
"""
import json
import os
from pathlib import Path
import subprocess
import time
from luda.desktop import Desktop
from luda.common import DesktopError
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts/toolkits';OUT.mkdir(parents=True,exist_ok=True)
results=[]
def record(toolkit,name,status,detail=None):
 row={'toolkit':toolkit,'case':name,'status':status,'detail':detail};results.append(row)
 print(json.dumps(row,ensure_ascii=False),flush=True)
def qualify(toolkit):
 out=OUT/toolkit;out.mkdir(exist_ok=True)
 env=dict(os.environ,QT_ACCESSIBILITY='1',QT_LINUX_ACCESSIBILITY_ALWAYS_ON='1',GTK_A11Y='atspi')
 log=(out/'fixture.log').open('w')
 p=subprocess.Popen(['/usr/bin/python3',str(ROOT/'tests'/f'{toolkit}_fixture.py'),str(out)],env=env,stdout=log,stderr=log)
 d=Desktop()
 original_ax=d.ax
 def ax_with_title(request,mutating=False):
  if request.get('op')=='inspect' and 'window_title' not in request:
   matches=[x for x in d.list_windows() if x['pid']==request['pid'] and x['bounds']==request['bounds']]
   if len(matches)==1:request={**request,'window_title':matches[0]['title']}
  return original_ax(request,mutating)
 d.ax=ax_with_title
 def state():
  time.sleep(.12);return json.loads((out/'state.json').read_text())
 def attempt(name,action,oracle=None):
  try:
   response=action()
   actual=oracle() if oracle else True
   deadline=time.monotonic()+1
   while not actual and time.monotonic()<deadline:
    time.sleep(.04);actual=oracle()
   supported=response.get('effect') in ('verified','dispatched') if 'effect' in response else True
   record(toolkit,name,'supported' if actual and supported else 'failed',{'response':response,'oracle':actual})
   return response
  except DesktopError as e:
   if toolkit=='qt' and name in ('insert-selection','astral-replace'):
    probe="""import sys,json
sys.path.insert(0,sys.argv[2]);import ax_worker as w
for n,_ in w.candidates(int(sys.argv[1])):
 if n.get_name()=='Toolkit text':
  t=n.get_text_iface();count=w.Atspi.Text.get_character_count(t)
  print(json.dumps({'count':count,'text_count':w.Atspi.Text.get_text(t,0,count),'text_all':w.Atspi.Text.get_text(t,0,-1),'caret':w.Atspi.Text.get_caret_offset(t)}))
"""
    raw=subprocess.run(['/usr/bin/python3','-c',probe,str(p.pid),str(ROOT/'src/luda')],capture_output=True,text=True,timeout=5)
    (out/(name+'-raw.json')).write_text(raw.stdout)
   record(toolkit,name,'unsupported' if e.code in ('UNSUPPORTED','NOT_EDITABLE','UNSUPPORTED_ACTION','AMBIGUOUS_ACCESSIBILITY_WINDOW') else 'failed',{'code':e.code,'message':str(e)})
  except Exception as e:record(toolkit,name,'failed',{'exception':type(e).__name__,'message':str(e)})
 try:
  w=None
  for _ in range(80):
   w=next((w for w in d.list_windows() if w['pid']==p.pid),None)
   if w:break
   if p.poll() is not None:raise RuntimeError('Fixture exited: '+(out/'fixture.log').read_text())
   time.sleep(.1)
  if w is None:raise RuntimeError('Fixture window did not appear')
  wid=w['window_id'];d.activate(wid);time.sleep(.3)
  tree=attempt('scoped-tree',lambda:d.inspect(wid))
  if not tree:
   script = """import json,sys,gi
sys.path.insert(0,sys.argv[2])
import ax_worker
rows=[]
for node,depth in ax_worker.candidates(int(sys.argv[1]),depth=3,limit=100):
 try:
  d=ax_worker.describe(node,int(sys.argv[1]));d['depth']=depth;rows.append(d)
 except Exception as e:rows.append({'error':str(e)})
print(json.dumps(rows))
"""
   raw=subprocess.run(['/usr/bin/python3','-c',script,str(p.pid),str(ROOT/'src/luda')],capture_output=True,text=True,timeout=5)
   (out/'raw-scope.json').write_text(json.dumps({'window':w,'raw':raw.stdout,'stderr':raw.stderr},indent=2))
   return
  (out/'inspect.json').write_text(json.dumps(tree,indent=2))
  nodes={}
  for n in tree['nodes']:nodes.setdefault(n['name'],n)
  editor=nodes.get('Toolkit text')
  if not editor:
   record(toolkit,'editor-available','unsupported',{'names':list(nodes)});return
  eid=editor['element_id']
  attempt('focus',lambda:d.element(eid,'focus'),lambda:state()['focused'])
  for i,text in enumerate(['alpha\nbeta\n','café 日本語 👩🏽\u200d💻 e\u0301\n','tabs\there\n','']):
   attempt('replace-'+str(i),lambda text=text:d.element(eid,'set',text=text),lambda text=text:state()['text']==text)
   if i==1:
    r=d.element(eid,'read');record(toolkit,'unicode-offset-contract','supported' if r['characters']==len(text) else 'failed',r)
  attempt('prepare-append',lambda:d.element(eid,'set',text='prefix '),lambda:state()['text']=='prefix ')
  attempt('append-at-current-caret',lambda:d.element(eid,'insert',text='日本語 👩🏽\u200d💻\n'),lambda:state()['text']=='prefix 日本語 👩🏽\u200d💻\n')
  attempt('prepare-insert',lambda:d.element(eid,'set',text='prefix SUFFIX'),lambda:state()['text']=='prefix SUFFIX')
  selected=attempt('select',lambda:d.element(eid,'select',start_offset=7,end_offset=13),lambda:state().get('selection',state().get('selection_utf16'))==[7,13])
  inserted='日本語 👩🏽\u200d💻\n\t'
  if selected and selected.get('exact_match'):
   attempt('insert-selection',lambda:d.element(eid,'insert',text=inserted),lambda:state()['text']=='prefix '+inserted)
  else:record(toolkit,'insert-selection','blocked','Selection prerequisite failed; insertion not attempted.')
  caret_ready=attempt('caret-zero',lambda:d.element(eid,'select',start_offset=0,end_offset=0))
  if caret_ready and caret_ready.get('exact_match'):
   before=state()['text']
   attempt('insert-caret',lambda:d.element(eid,'insert',text='BEFORE\n'),lambda:state()['text']=='BEFORE\n'+before)
  else:record(toolkit,'insert-caret','blocked','Caret prerequisite failed; insertion not attempted.')
  attempt('astral-prepare',lambda:d.element(eid,'set',text='A👩🏽\u200d💻Z'),lambda:state()['text']=='A👩🏽\u200d💻Z')
  astral_selected=attempt('astral-select',lambda:d.element(eid,'select',start_offset=1,end_offset=5))
  if astral_selected and astral_selected.get('exact_match'):
   attempt('astral-replace',lambda:d.element(eid,'insert',text='é'),lambda:state()['text']=='AéZ')
  else:record(toolkit,'astral-replace','blocked','Astral selection prerequisite failed; insertion not attempted.')
  disabled=nodes.get('Toolkit disabled')
  if disabled:
   try:d.element(disabled['element_id'],'invoke',action=(disabled.get('actions') or ['click'])[0])
   except DesktopError as e:record(toolkit,'disabled-refused','supported' if e.code=='NOT_INTERACTABLE' else 'failed',e.code)
   else:record(toolkit,'disabled-refused','failed')
  for wanted in (True,True,False):
   if 'Toolkit check' in nodes:attempt('check-'+str(wanted),lambda wanted=wanted:d.element(nodes['Toolkit check']['element_id'],'check',checked=wanted),lambda wanted=wanted:state()['checked']==wanted)
  for value in (42,0,100):
   if 'Toolkit value' in nodes:attempt('value-'+str(value),lambda value=value:d.element(nodes['Toolkit value']['element_id'],'value',value=value),lambda value=value:state()['value']==value)
  protected=[n for n in tree['nodes'] if n.get('protected')]
  record(toolkit,'protected-field-redacted','supported' if protected and all(n['name']=='[protected]' for n in protected) else 'failed')
  if protected:
   try:d.element(protected[0]['element_id'],'read')
   except DesktopError as e:record(toolkit,'protected-read-refused','supported' if e.code=='PROTECTED_FIELD' else 'failed',e.code)
   else:record(toolkit,'protected-read-refused','failed')
  button=nodes.get('Open toolkit dialog')
  if button and button.get('actions'):
   attempt('open-modal',lambda:d.element(button['element_id'],'invoke',action=button['actions'][0]),lambda:state()['dialog_visible'])
   time.sleep(.2)
   dialogs=[x for x in d.list_windows() if x['pid']==p.pid and x['window_id']!=wid]
   if dialogs:
    dialog=dialogs[-1];d.activate(dialog['window_id'])
    modal=attempt('modal-scoped-tree',lambda:d.inspect(dialog['window_id']))
    if modal:
     close=next((n for n in modal['nodes'] if n['name']=='Close toolkit dialog' and n.get('actions')),None)
     if close:attempt('close-modal',lambda:d.element(close['element_id'],'invoke',action=close['actions'][0]),lambda:not state()['dialog_visible'])
     else:record(toolkit,'modal-close-control','unsupported')
   else:record(toolkit,'modal-window-discovery','failed')
  else:record(toolkit,'modal-open-control','unsupported')
 finally:
  if p.poll() is None:p.terminate();p.wait(timeout=3)
  d.close();log.close()
for toolkit in ('qt','gtk4'):
 try:qualify(toolkit)
 except Exception as e:record(toolkit,'fixture','failed',{'exception':type(e).__name__,'message':str(e)})
(OUT/'results.json').write_text(json.dumps(results,indent=2,ensure_ascii=False))
print(json.dumps({s:sum(r['status']==s for r in results) for s in ('supported','unsupported','failed','blocked')}))
raise SystemExit(1 if any(r['status']=='failed' for r in results) else 0)
