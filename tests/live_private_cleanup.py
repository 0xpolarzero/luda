"""Private Xvfb: cleanup after pair removal must preserve matching human input."""
import ctypes as C
import json
import os
import select
import subprocess
import sys

from luda._x11_helper import _NativeX11
from luda._private_input import TOKEN_ENV
from luda.private_input import PrivateInput
from luda.common import DesktopError
from live_private_input_owner import keys, pointer


def run():
    readfd, writefd = os.pipe()
    server = subprocess.Popen(['Xvfb', '-displayfd', str(writefd), '-screen', '0', '640x480x24', '-nolisten', 'tcp'], pass_fds=(writefd,), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    os.close(writefd)
    owner = human = injector = None
    original = os.environ.get('DISPLAY')
    try:
        assert select.select([readfd], [], [], 3)[0]
        os.environ['DISPLAY'] = ':' + os.read(readfd, 32).decode().strip()
        human = _NativeX11()
        human.lib.XSync.argtypes = [C.c_void_p, C.c_int]
        human.lib.XKeysymToKeycode.argtypes = [C.c_void_p, C.c_ulong]
        human.lib.XKeysymToKeycode.restype = C.c_ubyte
        code = human.lib.XKeysymToKeycode(human.display, 0xffe3)
        test = C.CDLL('libXtst.so.6')
        test.XTestFakeKeyEvent.argtypes = [C.c_void_p, C.c_uint, C.c_int, C.c_ulong]
        test.XTestFakeButtonEvent.argtypes = [C.c_void_p, C.c_uint, C.c_int, C.c_ulong]
        test.XTestFakeKeyEvent(human.display, code, True, 0)
        test.XTestFakeButtonEvent(human.display, 1, True, 0)
        human.lib.XSync(human.display, False)
        before = keys(human), pointer(human)
        owner = PrivateInput()
        env = owner.environment()
        token = json.loads(env[TOKEN_ENV])
        source = 'from luda._keyboard_native import Keyboard; import json,sys; k=Keyboard(); print(json.dumps(k.client_resource()),flush=True); sys.stdin.read(); k.close()'
        injector = subprocess.Popen([sys.executable, '-c', source], stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env, text=True)
        assert select.select([injector.stdout], [], [], 3)[0]
        resource = json.loads(injector.stdout.readline())
        assert human._property(resource['xid'], '_LUDA_WINDOW_TOKEN', 9)
        owner.close()
        request = {'server_generation':token['generation'], 'client':resource}
        results = []
        for module, data in [('luda._keyboard_native', {'keycodes':[code]}), ('luda._pointer_native', {'button':'1'})]:
            result = subprocess.run([sys.executable, '-m', module, 'release'], input=json.dumps({**request, **data})+'\n', text=True, capture_output=True, timeout=3, env=env)
            receipt = json.loads(result.stdout)
            assert receipt == {'released':True, 'session_changed':False, 'cleanup_skipped':True, 'private_devices_removed':True}, receipt
            assert (keys(human), pointer(human)) == before
            results.append(receipt)
        try:
            assert not human._property(resource['xid'], '_LUDA_WINDOW_TOKEN', 9)
        except DesktopError as exc:
            assert exc.code == 'STALE_TARGET'
        # Different original generation proves replacement before trying to bind
        # the obsolete pair or disconnect an unrelated current-server resource.
        changed = {**request, 'server_generation':'0'*32, 'keycodes':[code]}
        receipt = json.loads(subprocess.check_output([sys.executable, '-m', 'luda._keyboard_native', 'release'], input=json.dumps(changed)+'\n', text=True, env=env, timeout=3))
        assert receipt == {'released':False, 'session_changed':True, 'cleanup_skipped':True}
        assert (keys(human), pointer(human)) == before
        test.XTestFakeButtonEvent(human.display, 1, False, 0)
        test.XTestFakeKeyEvent(human.display, code, False, 0)
        human.lib.XSync(human.display, False)
        print(json.dumps({'passed':True, 'checks':['removed-pair keyboard cleanup', 'removed-pair pointer cleanup', 'old nonce injector disconnected', 'matching human key/button retained', 'different-server proof before binding']}))
    finally:
        if injector:
            injector.stdin.close()
            injector.wait(timeout=3)
            injector.stdout.close()
        if owner: owner.close()
        if human: human.close()
        if original is None: os.environ.pop('DISPLAY', None)
        else: os.environ['DISPLAY'] = original
        os.close(readfd)
        server.terminate(); server.wait(timeout=3)

if __name__ == '__main__': run()
