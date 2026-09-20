"""Read-only native target and keyboard preflight shared by browser input."""
import json
import sys
from .common import DesktopError, run

class NativeInput:
    def focus(self,target):
        request={'target':target['xid'],'target_generation':target['generation']}
        result=json.loads(run([sys.executable,'-m','luda._keyboard_native','focus'],data=json.dumps(request).encode()+b'\n',timeout=2,max_output_bytes=4096))
        if result.get('code'):raise DesktopError(result['code'],'Agent browser focus failed.')

    def prepare_key(self, target, chord):
        # Read-only native target/generation, focus, held and latched state check.
        # Do not start an XTest injector inside the killable browser owner.
        request={'chord':chord,'target':target['xid'],'target_generation':target['generation']}
        result=json.loads(run([sys.executable,'-m','luda._keyboard_native','plan'],data=json.dumps(request).encode()+b'\n',timeout=1,max_output_bytes=16384))
        if result.get('code'):raise DesktopError(result['code'],'Native browser input preflight failed.')

