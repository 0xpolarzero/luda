"""Live worker semantics with a GTK-owned independent persisted oracle. Hold global flock."""
import json
from pathlib import Path
import subprocess
import time
from luda.desktop import Desktop
from luda.common import DesktopError
ROOT = Path(__file__).resolve().parents[1]
output = ROOT/'artifacts/semantic'
output.mkdir(parents=True, exist_ok=True)
p = subprocess.Popen(['/usr/bin/python3',str(ROOT/'tests/semantic_fixture.py'),str(output)])
d = Desktop(); results = []
def record(name, okay, detail=None):
    results.append({'case':name,'passed':bool(okay),'detail':detail})
    assert okay, (name,detail)
def state():
    time.sleep(.1)
    return json.loads((output/'state.json').read_text())
def reject(name, code, fn):
    try: fn()
    except DesktopError as exc: record(name,exc.code==code,exc.code)
    else: record(name,False)
try:
    for _ in range(50):
        w=next((w for w in d.list_windows() if w['pid']==p.pid),None)
        if w:break
        time.sleep(.1)
    assert w
    wid=w['window_id'];d.activate(wid);time.sleep(.3)
    tree=d.inspect(wid);(output/'inspect.json').write_text(json.dumps(tree,indent=2))
    nodes={n['name']:n for n in tree['nodes']};eid=nodes['Contract text']['element_id']
    def op(operation,**kw):return d.element(eid,operation,**kw)
    record('focus-state-verified',op('focus')['effect']=='verified')
    samples=['alpha\nbeta\n','café 日本語 👩🏽\u200d💻 e\u0301\n','\t \n\n','']
    for i,text in enumerate(samples):
        op('set',text='prefix SUFFIX');op('select',start_offset=7,end_offset=13)
        r=op('insert',text=text)
        record('replace-selection-'+str(i),r['exact_match'] and r['caret_verified'] and state()['text']=='prefix '+text and state()['caret']==7+len(text),r)
        op('select',start_offset=0,end_offset=0)
        r=op('insert',text=text)
        record('insert-caret-'+str(i),r['exact_match'] and state()['text']==text+'prefix '+text,r)
    op('set',text='abcdef');r=op('select',start_offset=2,end_offset=5)
    record('selection-independent',r['exact_match'] and state()['selection']==[2,5])
    r=op('read');record('read-selection-contract',r['selections']==[{'start_offset':2,'end_offset':5}] and r['offset_units']=='Unicode code points',r)
    reject('negative-selection','INVALID_ARGUMENT',lambda:op('select',start_offset=-1,end_offset=0))
    reject('reversed-selection','INVALID_ARGUMENT',lambda:op('select',start_offset=4,end_offset=2))
    reject('oversize-selection','INVALID_ARGUMENT',lambda:op('select',start_offset=0,end_offset=7))
    reject('boolean-selection','INVALID_ARGUMENT',lambda:op('select',start_offset=False,end_offset=0))
    reject('protected-insert','PROTECTED_FIELD',lambda:d.element(nodes['[protected]']['element_id'],'insert',text='x'))
    reject('protected-select','PROTECTED_FIELD',lambda:d.element(nodes['[protected]']['element_id'],'select',start_offset=0,end_offset=0))
    reject('hidden-insert','NOT_INTERACTABLE',lambda:d.element(nodes['Hidden text']['element_id'],'insert',text='x'))
    reject('invalid-unicode','UNSUPPORTED_TEXT',lambda:op('insert',text='\ud800'))
    reject('CR-insert','UNSUPPORTED_TEXT',lambda:op('insert',text='\r'))
    reject('NUL-insert','UNSUPPORTED_TEXT',lambda:op('insert',text='\0'))
    for wanted in (True,True,False):
        r=d.element(nodes['Semantic check']['element_id'],'check',checked=wanted)
        record('check-'+str(len(results)),r['effect']=='verified' and state()['checked']==wanted,r)
    for value in (0,42,100):
        r=d.element(nodes['Semantic value']['element_id'],'value',value=value)
        record('value-'+str(value),r['exact_match'] and state()['value']==value,r)
    reject('value-outside-range','OUT_OF_BOUNDS',lambda:d.element(nodes['Semantic value']['element_id'],'value',value=101))
    reject('value-NaN','INVALID_ARGUMENT',lambda:d.element(nodes['Semantic value']['element_id'],'value',value=float('nan')))
    for wanted in (True,True,False):
        r=d.element(nodes['Semantic expander']['element_id'],'expand',expanded=wanted)
        record('expand-'+str(len(results)),r['effect']=='verified' and state()['expanded']==wanted,r)
    bounds={k:w[k] for k in ('pid','start','bounds','frame_bounds')}
    r=d.ax({'op':'inspect',**bounds,'filters':{'name':'semantic','states':['showing']}})
    record('filtered-tree',len(r['nodes'])==4 and all('semantic' in n['name'].lower() for n in r['nodes']),r)
    r=d.ax({'op':'inspect',**bounds,'max_depth':0})
    record('depth-budget-reported',len(r['nodes'])==1 and r['truncation']['depth_pruned'],r)
    r=d.ax({'op':'inspect',**bounds,'filters':{'name':'does not exist'}})
    record('empty-filter-accessibility-available',r['available'] and not r['nodes'],r)
finally:
    if p.poll() is None:p.terminate();p.wait(timeout=3)
    d.close()
    (output/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2))
    print(json.dumps(results,ensure_ascii=False))
