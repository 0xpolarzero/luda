"""Read-only native target and keyboard preflight shared by browser input."""
import json
import os
import time
import sys
from .common import DesktopError, run

class NativeInput:
    def focus(self,target):
        request={'target':target['xid'],'target_generation':target['generation']}
        if os.environ.get('LUDA_INPUT_ROUTE') == 'shared':
            # Only the compatibility owner needs foreground focus. Normal CDP
            # text operations retain their private/background route.
            run(['xdotool','windowactivate',str(target['xid'])],timeout=2,effect='uncertain')
        deadline=time.monotonic()+1
        while True:
            result=json.loads(run([sys.executable,'-m','luda._keyboard_native','focus'],data=json.dumps(request).encode()+b'\n',timeout=2,max_output_bytes=4096))
            if not result.get('code'):return
            if result['code']!='FOCUS_CHANGED' or time.monotonic()>=deadline:
                raise DesktopError(result['code'],'Browser focus failed.')
            time.sleep(.03)

    def prepare_key(self, target, chord):
        # Read-only native target/generation, focus, held and latched state check.
        # Do not start an XTest injector inside the killable browser owner.
        request={'chord':chord,'target':target['xid'],'target_generation':target['generation']}
        result=json.loads(run([sys.executable,'-m','luda._keyboard_native','plan'],data=json.dumps(request).encode()+b'\n',timeout=1,max_output_bytes=16384))
        if result.get('code'):raise DesktopError(result['code'],'Native browser input preflight failed.')

