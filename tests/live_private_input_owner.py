"""Private Xvfb lifecycle/device-state oracle; does not touch an existing desktop."""
import ctypes as C
import json
import os
import select
import subprocess
import time

from luda._private_input import Devices, bind_private_input, TOKEN_ENV
from luda._x11_helper import _NativeX11
from luda.private_input import PrivateInput


def wait_absent(devices, name):
    deadline = time.monotonic() + 3
    while any(d['name'].startswith(name + ' ') for d in devices.devices()):
        assert time.monotonic() < deadline, 'owned devices survived cleanup'
        time.sleep(.02)


def pointer(x):
    x.lib.XQueryPointer.argtypes = [C.c_void_p, C.c_ulong, C.POINTER(C.c_ulong), C.POINTER(C.c_ulong)] + [C.POINTER(C.c_int)] * 4 + [C.POINTER(C.c_uint)]
    root, child, mask = C.c_ulong(), C.c_ulong(), C.c_uint()
    coords = [C.c_int() for _ in range(4)]
    assert x.lib.XQueryPointer(x.display, x.root, C.byref(root), C.byref(child), *[C.byref(v) for v in coords], C.byref(mask))
    return [v.value for v in coords], mask.value


def keys(x):
    value = C.create_string_buffer(32)
    x.lib.XQueryKeymap.argtypes = [C.c_void_p, C.c_void_p]
    x.lib.XQueryKeymap(x.display, value)
    return value.raw


def run():
    readfd, writefd = os.pipe()
    server = subprocess.Popen(['Xvfb', '-displayfd', str(writefd), '-screen', '0', '640x480x24', '-nolisten', 'tcp'], pass_fds=(writefd,), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    os.close(writefd)
    owner = human = agent = None
    old = os.environ.get('DISPLAY')
    try:
        assert select.select([readfd], [], [], 3)[0], 'Xvfb startup timeout'
        os.environ['DISPLAY'] = ':' + os.read(readfd, 32).decode().strip()
        human = _NativeX11()
        devices = Devices(human)
        baseline = devices.devices()
        owner = PrivateInput()
        env = owner.environment()
        identity = json.loads(env[TOKEN_ENV])
        agent = _NativeX11()
        binding = bind_private_input(agent, env[TOKEN_ENV])
        test = C.CDLL('libXtst.so.6')
        test.XTestFakeMotionEvent.argtypes = [C.c_void_p, C.c_int, C.c_int, C.c_int, C.c_ulong]
        test.XTestFakeKeyEvent.argtypes = [C.c_void_p, C.c_uint, C.c_int, C.c_ulong]
        human.lib.XSync.argtypes = [C.c_void_p, C.c_int]
        before = pointer(human)
        test.XTestFakeMotionEvent(agent.display, -1, 123, 234, 0)
        agent.lib.XSync(agent.display, False)
        assert pointer(human) == before, 'agent moved human pointer'
        assert pointer(agent)[0][:2] == [123, 234], 'agent pointer did not move'
        # Held keys are isolated in both directions, including identical keycodes.
        test.XTestFakeKeyEvent(human.display, 38, True, 0)
        human.lib.XSync(human.display, False)
        human_held = keys(human)
        assert human_held != bytes(32)
        assert keys(agent) == bytes(32), 'human hold contaminated private keyboard'
        test.XTestFakeKeyEvent(agent.display, 38, True, 0)
        test.XTestFakeKeyEvent(agent.display, 38, False, 0)
        agent.lib.XSync(agent.display, False)
        assert keys(human) == human_held, 'agent released human key'
        assert keys(agent) == bytes(32)
        owner.close()
        wait_absent(devices, identity['name'])
        assert keys(human) == human_held, 'cleanup released human key'
        assert devices.devices() == baseline
        # Owner SIGKILL still triggers its independent cleanup watchdog.
        env = owner.environment()
        identity = json.loads(env[TOKEN_ENV])
        owner._process.kill()
        owner._process.wait()
        wait_absent(devices, identity['name'])
        assert devices.devices() == baseline
        test.XTestFakeKeyEvent(human.display, 38, False, 0)
        human.lib.XSync(human.display, False)
        print(json.dumps({'passed': True, 'checks': ['private pointer', 'private keyboard', 'same-key release isolation', 'normal cleanup', 'owner SIGKILL cleanup', 'unchanged human devices']}))
    finally:
        if owner: owner.close()
        if agent: agent.close()
        if human: human.close()
        if old is None: os.environ.pop('DISPLAY', None)
        else: os.environ['DISPLAY'] = old
        os.close(readfd)
        server.terminate()
        server.wait(timeout=3)


if __name__ == '__main__':
    run()
