"""Read real D-Bus hints on a private bus; never lock the user's desktop."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
from luda.session_state import session_state

if len(sys.argv)==1:
    env=dict(os.environ);env.pop('XDG_SESSION_ID',None)
    subprocess.run(['dbus-run-session','--',sys.executable,__file__,'private'],env=env,check=True,timeout=15)
else:
    assert session_state()['state']=='unknown'
    with tempfile.TemporaryDirectory() as directory:
        base=Path(directory);flag=base/'active';flag.write_text('true');ready=base/'ready';calls=base/'calls'
        child=subprocess.Popen(['/usr/bin/python3',str(Path(__file__).with_name('session_state_fixture.py')),str(flag),str(ready),str(calls)])
        try:
            deadline=time.monotonic()+4
            while not ready.exists():
                assert time.monotonic()<deadline,'private provider not ready';time.sleep(.02)
            result=session_state();assert result['state']=='screensaver_active' and result['input_ready'] is False,result
            flag.write_text('false')
            result=session_state();assert result['state']=='inactive' and result['input_ready'] is None,result
            assert calls.read_text().splitlines()==['GetActive','GetActive']
            print(json.dumps({'unavailable':'unknown','active':'screensaver_active','inactive':'not proof of unlocked','provider_methods':['GetActive','GetActive']}))
        finally:
            child.terminate();child.wait(timeout=3)
