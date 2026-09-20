"""Bounded repeated-observation/resource regression on a private desktop."""
import gc
import json
import os
from pathlib import Path
import subprocess
import time
from luda.desktop import Desktop

if os.environ.get('LUDA_ISOLATED_TEST_DISPLAY') != '1':
    raise SystemExit('Requires an explicitly isolated test desktop.')
fixture='''import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk
w=Gtk.Window(title='Luda resource matrix');w.set_default_size(800,600)
scroll=Gtk.ScrolledWindow();box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
for i in range(520):box.pack_start(Gtk.Button(label='Control '+str(i)),False,False,0)
scroll.add(box);w.add(scroll);w.connect('destroy',Gtk.main_quit);w.show_all();Gtk.main()
'''
def usage():
    status=Path('/proc/self/status').read_text()
    rss=int(next(row.split()[1] for row in status.splitlines() if row.startswith('VmRSS:')))
    children=set()
    for task in Path('/proc/self/task').iterdir():
        children.update((task/'children').read_text().split())
    return {'fds':len(list(Path('/proc/self/fd').iterdir())),'rss_kib':rss,'children':sorted(children)}
app=subprocess.Popen(['/usr/bin/python3','-c',fixture],stdout=subprocess.DEVNULL)
d=Desktop();samples=[]
try:
    deadline=time.monotonic()+8
    while True:
        w=next((v for v in d.list_windows() if v['pid']==app.pid),None)
        if w:break
        assert time.monotonic()<deadline,'fixture unavailable'
        time.sleep(.05)
    for index in range(28):
        with d.transaction():
            d.activate(w['window_id'])
            tree=d.inspect(w['window_id'],limit=500)
            assert len(tree['nodes'])==500, len(tree['nodes'])
            snap=d.observe(640)
            assert snap['image_size']['width']==640
            del snap,tree
        gc.collect()
        sample=usage();sample.update(iteration=index,elements=len(d.elements),snapshots=len(d.snapshots))
        assert sample['elements']<=4000 and sample['snapshots']<=16,sample
        assert sample['children']==[str(app.pid)],sample
        samples.append(sample)
    # Warm-up allocations are not leakage; compare the steady repeated phase.
    steady=samples[5:]
    assert max(v['fds'] for v in steady)-min(v['fds'] for v in steady)<=1,samples
    assert max(v['rss_kib'] for v in steady)-min(v['rss_kib'] for v in steady)<128*1024,samples
    d.close()
    assert not d.elements and not d.snapshots
    closed=usage()
    assert closed['fds']<samples[-1]['fds'],(closed,samples[-1])
    print(json.dumps({'iterations':28,'nodes_per_inspection':500,'samples':samples,'after_close':closed,
                      'scope':'Short repeated-load regression, not an hours-long soak or hard RSS ceiling.'},indent=2))
finally:
    d.close();app.terminate();app.wait(timeout=5)
