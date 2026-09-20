"""Real GTK table/tree qualification with independent app-persisted oracle."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import tempfile
from luda.desktop import Desktop
from luda.common import DesktopError
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'scripts'))
from headless_tests import stop
from qualify import source_fingerprint
OUT=ROOT/'artifacts/data';OUT.mkdir(parents=True,exist_ok=True)
if os.getuid()==0 or os.environ.get('LUDA_ISOLATED_TEST_DISPLAY')!='1':raise SystemExit('Requires ordinary UID and private display')
scratch=tempfile.TemporaryDirectory(prefix='luda-data-xdg-')
for key,suffix in [('XDG_CONFIG_HOME','config'),('XDG_DATA_HOME','data'),('XDG_CACHE_HOME','cache'),('XDG_RUNTIME_DIR','runtime')]:
 path=Path(scratch.name,suffix);path.mkdir(mode=0o700);os.environ[key]=str(path)
os.environ['XDG_CONFIG_DIRS']=os.environ['XDG_CONFIG_HOME'];os.environ['GSETTINGS_BACKEND']='memory'
os.environ.pop('AT_SPI_BUS_ADDRESS',None)
records=[];source=source_fingerprint(ROOT)
def record(case,passed,**details):
 row={'case':case,'passed':bool(passed),**details};records.append(row);print(json.dumps(row),flush=True)
def state():time.sleep(.12);return json.loads((OUT/'state.json').read_text())
with (OUT/'fixture.log').open('w') as log:
 wm=subprocess.Popen(['xfwm4','--compositor=off'],stdout=log,stderr=log,start_new_session=True)
 p=subprocess.Popen(['/usr/bin/python3',str(ROOT/'tests/data_fixture.py'),str(OUT)],stdout=log,stderr=log,start_new_session=True)
 d=Desktop()
 try:
  deadline=time.monotonic()+10
  while True:
   found=[w for w in d.list_windows() if w['pid']==p.pid]
   if len(found)==1:break
   if time.monotonic()>deadline:raise RuntimeError('Fixture window unavailable')
   time.sleep(.1)
  wid=found[0]['window_id'];d.activate(wid)
  def inspect(**kw):return d.inspect(wid,**kw)
  tree=inspect(limit=500);(OUT/'initial-tree.json').write_text(json.dumps(tree,indent=2))
  record('bounded-large-table-inspection',len(tree['nodes'])<=500 and tree['truncated'],nodes=len(tree['nodes']),truncation=tree['truncation'])
  def nodes_named(name):return [n for n in inspect(limit=500,name=name)['nodes'] if n['name']==name]
  def node(name):
   nodes=nodes_named(name)
   if len(nodes)!=1:raise RuntimeError(f'Expected unique {name}: {len(nodes)}')
   return nodes[0]
  def invoke(name):
   n=node(name);return d.element(n['element_id'],'invoke',action=n['actions'][0])
  def action(case,fn,oracle):
   try:
    response=fn();actual=oracle();record(case,response.get('effect') in ('verified','dispatched') and actual,response=response,oracle=actual)
   except DesktopError as exc:record(case,False,code=exc.code,effect=exc.effect)
  filtered=inspect(limit=10,name='Record 0030');record('filter-does-not-overclaim-traversal',all('Record 0030' in n['name'] for n in filtered['nodes']) and filtered['truncated'],truncation=filtered['truncation'])
  long_node=node('x'*300);invoke('Rename long identity');before=state().get('identity_clicks',0)
  try:r=d.element(long_node['element_id'],'invoke',action=long_node['actions'][0]);record('long-name-suffix-stale',False,response=r)
  except DesktopError as exc:record('long-name-suffix-stale',exc.code=='STALE_TARGET' and state().get('identity_clicks',0)==before,code=exc.code)
  fresh_long=node('x'*300);response=d.element(fresh_long['element_id'],'invoke',action=fresh_long['actions'][0])
  record('long-name-fresh-handle-and-private-digest',state().get('identity_clicks',0)==before+1 and 'name_fingerprint' not in fresh_long,response=response)
  off=node('Record 0030');before=state()['selected_id']
  try:r=d.element(off['element_id'],'choose');record('offscreen-row-refused',False,response=r,oracle=state())
  except DesktopError as exc:record('offscreen-row-refused',exc.code=='NOT_INTERACTABLE' and state()['selected_id']==before,code=exc.code,states=off['states'])
  visible=node('Record 0000');action('choose-visible-row',lambda:d.element(visible['element_id'],'choose'),lambda:state()['selected_id']==0)
  invoke('Reverse sort')
  try:
   r=d.element(visible['element_id'],'choose');actual=state();record('sort-old-handle-preserves-meaning-or-refuses',r.get('effect')=='verified' and actual['selected_id']==0,response=r,oracle=actual)
  except DesktopError as exc:record('sort-old-handle-preserves-meaning-or-refuses',exc.code in ('STALE_TARGET','NOT_INTERACTABLE'),code=exc.code)
  invoke('Reset data');old=node('Record 0000');invoke('Filter first ten');before=state()['selected_id']
  try:r=d.element(old['element_id'],'choose');record('filtered-out-handle-refused',False,response=r,oracle=state())
  except DesktopError as exc:record('filtered-out-handle-refused',exc.code in ('STALE_TARGET','NOT_INTERACTABLE') and state()['selected_id']==before,code=exc.code)
  invoke('Reset data')
  lazy=node('Lazy group')
  action('lazy-expand',lambda:d.element(lazy['element_id'],'expand',expanded=True),lambda:state()['expanded'] and state()['lazy_loaded'])
  child=nodes_named('Lazy child 0');record('lazy-children-fresh-inspection',len(child)==1)
  action('lazy-collapse',lambda:d.element(node('Lazy group')['element_id'],'expand',expanded=False),lambda:not state()['expanded'])
  cell=node('Value 0000');before=state()['edited']
  try:r=d.element(cell['element_id'],'set',text='must not replace table');record('cell-text-refuses-whole-widget-replacement',False,response=r)
  except DesktopError as exc:record('cell-text-refuses-whole-widget-replacement',exc.code in ('UNSUPPORTED','NOT_EDITABLE') and state()['edited']==before,code=exc.code)
  if 'edit' in cell.get('actions',[]):
   edit_response=d.element(cell['element_id'],'invoke',action='edit');time.sleep(.2)
   entries=[n for n in inspect(limit=500)['nodes'] if n['role'] in ('entry','text') and 'editable' in n['states']]
   if len(entries)==1:
    d.type_text(entries[0]['element_id'],'Edited exact 日本語',mode='replace');d.key(wid,'Return')
    record('editable-cell-commit',state()['edited'].get('0')=='Edited exact 日本語',oracle=state())
   else:record('editable-cell-commit',False,reason='No unique editable child after edit action',entries=entries,oracle=state(),response=edit_response)
  else:record('editable-cell-commit',False,reason='No edit action')
  # Pointer scrolling is anchored to a fresh screenshot, followed by fresh AX lookup.
  table=node('Records table');bounds=table.get('bounds');snapshot=d.observe(max_width=1600)
  if bounds:
   x=(bounds['x']+bounds['width']//2)*snapshot['image_size']['width']/snapshot['desktop_size']['width'];y=(bounds['y']+bounds['height']//2)*snapshot['image_size']['height']/snapshot['desktop_size']['height']
   before=state()['visible_range'];d.pointer(wid,snapshot['snapshot_id'],x,y,kind='scroll',direction='down',count=8)
   after=state()['visible_range'];record('scroll-updates-visible-rows',before!=after,before=before,after=after)
   fresh=inspect(limit=500)
   def intersects(n):
    b=n.get('bounds',{})
    return b and max(b['x'],bounds['x'])<min(b['x']+b['width'],bounds['x']+bounds['width']) and max(b['y'],bounds['y'])<min(b['y']+b['height'],bounds['y']+bounds['height'])
   showing=[n for n in fresh['nodes'] if n['name'].startswith('Record ') and 'showing' in n['states'] and intersects(n)]
   if showing:
    n=showing[-1];identifier=int(n['name'].split()[-1]);action('scroll-reacquire-row',lambda:d.element(n['element_id'],'choose'),lambda:state()['selected_id']==identifier)
   else:record('scroll-reacquire-row',False,reason='No showing row within bounded traversal')
 except Exception as exc:
  import traceback
  record('suite-completion',False,error=''.join(traceback.format_exception(exc)))
 finally:d.close();stop(p);stop(wm)
after=source_fingerprint(ROOT);record('source-unchanged',source==after)
(OUT/'results.json').write_text(json.dumps({'source_before':source,'source_after':after,'uid':os.getuid(),'records':records},indent=2))
scratch.cleanup()
raise SystemExit(int(not all(x['passed'] for x in records)))
