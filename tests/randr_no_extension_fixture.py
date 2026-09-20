"""Semantic tools remain usable when screenshot topology validation is unavailable."""
import json
from pathlib import Path
import subprocess
import sys
import time
from luda.common import DesktopError,stop_process
from luda.desktop import Desktop

root=Path(__file__).resolve().parents[1];out=Path(sys.argv[1])
wm=subprocess.Popen(['xfwm4','--compositor=off'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
app=None;desktop=None
try:
    deadline=time.monotonic()+5
    while subprocess.run(['wmctrl','-m'],capture_output=True,timeout=2).returncode:
        assert time.monotonic()<deadline
        time.sleep(.05)
    app=subprocess.Popen(['/usr/bin/python3',str(root/'tests/fixture.py'),str(out)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    desktop=Desktop();desktop.control.set_paused(False)
    deadline=time.monotonic()+7
    while True:
        window=next((w for w in desktop.list_windows() if w['pid']==app.pid),None)
        if window:break
        assert time.monotonic()<deadline
        time.sleep(.05)
    desktop.activate(window['window_id'])
    tree=desktop.inspect(window['window_id'],500)
    field=next(n for n in tree['nodes'] if n['name']=='Contract text')
    try:desktop.observe()
    except DesktopError as error:assert error.code=='TOPOLOGY_UNAVAILABLE',error.code
    else:raise AssertionError('Screenshot accepted without layout validation')
    wanted='Semantic input after unavailable RandR\n日本語'
    response=desktop.type_text(field['element_id'],wanted,mode='replace')
    assert response['exact_match']
    deadline=time.monotonic()+3
    while not (out/'state.json').exists() or json.loads((out/'state.json').read_text())['text']!=wanted:
        assert time.monotonic()<deadline
        time.sleep(.02)
    result={'screenshot':'TOPOLOGY_UNAVAILABLE','semantic_tree':True,'semantic_exact_type':True,'independent_app_oracle':True}
    (out/'semantic-result.json').write_text(json.dumps(result))
    print(json.dumps(result))
finally:
    if desktop:desktop.close()
    for child in (app,wm):
        if child:stop_process(child)
