"""XI2 private master-pair ownership and connection binding (internal only)."""
import ctypes as C
import json
import os
import re
import secrets
import select
import subprocess
import sys

from .common import DesktopError
from ._x11_helper import _NativeX11, _decode_window_token

TOKEN_ENV = 'LUDA_PRIVATE_INPUT'
ROUTE_ENV = 'LUDA_INPUT_ROUTE'


def input_route():
    route = os.environ.get(ROUTE_ENV, 'private')
    if route not in ('private', 'shared'):
        raise DesktopError('INPUT_UNAVAILABLE', 'Unknown internal input route; no input sent.')
    return route


def validate_route(request):
    route = input_route()
    if request.get('input_route', 'private') != route:
        raise DesktopError('INPUT_UNAVAILABLE', 'Input ownership route changed; no input sent or released.')
    return route


class DeviceInfo(C.Structure):
    _fields_ = [('deviceid', C.c_int), ('name', C.c_char_p), ('use', C.c_int),
                ('attachment', C.c_int), ('enabled', C.c_int), ('num_classes', C.c_int),
                ('classes', C.c_void_p)]


class AddMaster(C.Structure):
    _fields_ = [('type', C.c_int), ('name', C.c_char_p), ('send_core', C.c_int), ('enable', C.c_int)]


class RemoveMaster(C.Structure):
    _fields_ = [('type', C.c_int), ('deviceid', C.c_int), ('return_mode', C.c_int),
                ('return_pointer', C.c_int), ('return_keyboard', C.c_int)]


def decode_token(raw):
    try:
        token = json.loads(raw)
        if (not isinstance(token, dict) or set(token) != {'name', 'pointer', 'keyboard', 'generation'}
                or not isinstance(token['name'], str) or not re.fullmatch(r'luda-[0-9a-f]{32}', token['name'])
                or not isinstance(token['generation'], str) or not re.fullmatch(r'[0-9a-f]{32}', token['generation'])
                or any(type(token[k]) is not int or not 2 <= token[k] <= 65535 for k in ('pointer', 'keyboard'))
                or token['pointer'] == token['keyboard']):
            raise ValueError()
        return token
    except (ValueError, TypeError, KeyError):
        raise DesktopError('INPUT_UNAVAILABLE', 'Private input identity is unavailable; no shared input fallback.') from None


class Devices:
    def __init__(self, native):
        self.x = native
        self.xi = C.CDLL('libXi.so.6')
        self.x.lib.XSync.argtypes = [C.c_void_p, C.c_int]
        self.x.lib.XGrabServer.argtypes = [C.c_void_p]
        self.x.lib.XUngrabServer.argtypes = [C.c_void_p]
        self.xi.XIQueryVersion.argtypes = [C.c_void_p, C.POINTER(C.c_int), C.POINTER(C.c_int)]
        self.xi.XIQueryDevice.argtypes = [C.c_void_p, C.c_int, C.POINTER(C.c_int)]
        self.xi.XIQueryDevice.restype = C.POINTER(DeviceInfo)
        self.xi.XIFreeDeviceInfo.argtypes = [C.POINTER(DeviceInfo)]
        self.xi.XIChangeHierarchy.argtypes = [C.c_void_p, C.c_void_p, C.c_int]
        self.xi.XISetClientPointer.argtypes = [C.c_void_p, C.c_ulong, C.c_int]
        self.xi.XIGetClientPointer.argtypes = [C.c_void_p, C.c_ulong, C.POINTER(C.c_int)]
        self.xi.XISetFocus.argtypes = [C.c_void_p, C.c_int, C.c_ulong, C.c_ulong]
        self.xi.XIGetFocus.argtypes = [C.c_void_p, C.c_int, C.POINTER(C.c_ulong)]
        major, minor = C.c_int(2), C.c_int(0)
        if self.xi.XIQueryVersion(self.x.display, C.byref(major), C.byref(minor)) != 0 or major.value < 2:
            raise DesktopError('INPUT_UNAVAILABLE', 'XI2 private input is unavailable; no shared input fallback.')

    def devices(self):
        count = C.c_int()
        raw = self.xi.XIQueryDevice(self.x.display, 0, C.byref(count))
        if not raw:
            raise DesktopError('INPUT_UNAVAILABLE', 'Cannot inspect private input devices.')
        try:
            return [{'id': d.deviceid, 'name': d.name.decode('utf-8', errors='replace'),
                     'use': d.use, 'attachment': d.attachment, 'enabled': bool(d.enabled)}
                    for d in raw[:count.value]]
        finally:
            self.xi.XIFreeDeviceInfo(raw)

    def generation(self):
        # Validation runs inside an outer server grab. window_tokens() would
        # grab/ungrab internally, releasing that outer protection prematurely.
        prop = self.x._property(self.x.root, '_LUDA_WINDOW_TOKEN', 9)
        value = _decode_window_token(*prop) if prop else None
        if value is None:
            raise DesktopError('SESSION_CHANGED', 'Private input server identity is missing.')
        return value

    def validate(self, token):
        if self.generation() != token['generation']:
            raise DesktopError('SESSION_CHANGED', 'Private input belongs to a previous X server.')
        devices = {d['id']: d for d in self.devices()}
        for kind, use, suffix, paired in [('pointer', 1, ' pointer', 'keyboard'), ('keyboard', 2, ' keyboard', 'pointer')]:
            d = devices.get(token[kind])
            if not d or d['name'] != token['name'] + suffix or d['use'] != use or d['attachment'] != token[paired] or not d['enabled']:
                raise DesktopError('INPUT_UNAVAILABLE', 'Private input devices disappeared or changed; no shared input fallback.')
        return token

    def create(self, name):
        info = AddMaster(1, name.encode(), 0, 1)
        if self.xi.XIChangeHierarchy(self.x.display, C.byref(info), 1) != 0:
            raise DesktopError('INPUT_UNAVAILABLE', 'Cannot create private input devices.')
        self.x.lib.XSync(self.x.display, False)
        devices = {d['name']: d for d in self.devices()}
        try:
            token = dict(name=name, pointer=devices[name + ' pointer']['id'],
                         keyboard=devices[name + ' keyboard']['id'], generation=self.generation())
        except KeyError:
            raise DesktopError('INPUT_UNAVAILABLE', 'Private input creation did not produce a master pair.') from None
        return self.validate(token)

    def remove(self, token):
        # An ID cannot be removed/reallocated between identity validation and removal.
        self.x.lib.XGrabServer(self.x.display)
        try:
            try:
                self.validate(token)
            except DesktopError:
                return False
            # Floating slaves avoids attaching any device to the human pair.
            info = RemoveMaster(2, token['pointer'], 2, 0, 0)
            self.xi.XIChangeHierarchy(self.x.display, C.byref(info), 1)
            self.x.lib.XSync(self.x.display, False)
            return True
        finally:
            self.x.lib.XUngrabServer(self.x.display)
            self.x.lib.XSync(self.x.display, False)


class Binding:
    route = 'private'
    def __init__(self, native, token):
        self.devices = Devices(native)
        self.token = self.devices.validate(token)
        self.pointer, self.keyboard = token['pointer'], token['keyboard']
        self.devices.xi.XISetClientPointer(native.display, 0, self.pointer)
        native.lib.XSync(native.display, False)
        selected = C.c_int()
        if not self.devices.xi.XIGetClientPointer(native.display, 0, C.byref(selected)) or selected.value != self.pointer:
            raise DesktopError('INPUT_UNAVAILABLE', 'Private input connection binding failed.')

    def validate(self):
        self.devices.validate(self.token)
        selected = C.c_int()
        if (not self.devices.xi.XIGetClientPointer(self.devices.x.display, 0, C.byref(selected))
                or selected.value != self.pointer):
            raise DesktopError('INPUT_UNAVAILABLE', 'Private input connection binding changed; no input sent.')
        return self.token

    def focus(self, window):
        self.validate()
        if type(window) is not int or not 0 < window <= 0xffffffff:
            raise DesktopError('INVALID_ARGUMENT', 'Invalid private keyboard focus target.')
        x = self.devices.x
        self.devices.xi.XISetFocus(x.display, self.keyboard, window, 0)
        x.lib.XSync(x.display, False)
        if self.focus_window() != window:
            raise DesktopError('FOCUS_CHANGED', 'Private keyboard focus could not be established.')

    def focus_window(self):
        self.validate()
        window = C.c_ulong()
        if self.devices.xi.XIGetFocus(self.devices.x.display, self.keyboard, C.byref(window)) != 0:
            raise DesktopError('INPUT_UNAVAILABLE', 'Cannot read private keyboard focus.')
        return window.value


class SharedBinding:
    """Explicit foreground compatibility route; never selected by token failure."""
    route = 'shared'

    def __init__(self, native):
        self.devices = Devices(native)
        native.window_tokens([native.root])  # Initialize before guarded validation.
        self.generation = self.devices.generation()
        selected = C.c_int()
        if not self.devices.xi.XIGetClientPointer(native.display, 0, C.byref(selected)):
            raise DesktopError('INPUT_UNAVAILABLE', 'Cannot identify shared input devices.')
        found = {d['id']: d for d in self.devices.devices()}
        pointer = found.get(selected.value)
        keyboard = found.get(pointer['attachment']) if pointer else None
        if (not pointer or not keyboard or pointer['name'] != 'Virtual core pointer'
                or keyboard['name'] != 'Virtual core keyboard' or pointer['use'] != 1
                or keyboard['use'] != 2 or keyboard['attachment'] != pointer['id']
                or not pointer['enabled'] or not keyboard['enabled']):
            raise DesktopError('INPUT_UNAVAILABLE', 'Default connection is not bound to the shared core pair.')
        self.pointer, self.keyboard = pointer['id'], keyboard['id']
        self._identity = (dict(pointer), dict(keyboard))
        native.lib.XGetInputFocus.argtypes = [C.c_void_p, C.POINTER(C.c_ulong), C.POINTER(C.c_int)]
        self.validate()

    def validate(self):
        if self.devices.generation() != self.generation:
            raise DesktopError('SESSION_CHANGED', 'Shared input belongs to a previous X server.')
        selected = C.c_int()
        if (not self.devices.xi.XIGetClientPointer(self.devices.x.display, 0, C.byref(selected))
                or selected.value != self.pointer):
            raise DesktopError('INPUT_UNAVAILABLE', 'Shared input connection binding changed; no input sent.')
        found = {d['id']: d for d in self.devices.devices()}
        if tuple(found.get(device) for device in (self.pointer, self.keyboard)) != self._identity:
            raise DesktopError('INPUT_UNAVAILABLE', 'Shared input devices changed; no input sent.')

    def focus_window(self):
        self.validate()
        window, revert = C.c_ulong(), C.c_int()
        self.devices.x.lib.XGetInputFocus(self.devices.x.display, C.byref(window), C.byref(revert))
        return window.value


def bind_private_input(native, token=None):
    if input_route() == 'shared':
        return SharedBinding(native)
    return Binding(native, decode_token(os.environ.get(TOKEN_ENV, '') if token is None else token))


def main():
    native = None
    token = None
    watchdog = None
    try:
        native = _NativeX11()
        devices = Devices(native)
        if sys.argv[1:] == ['watchdog']:
            # Reservation precedes creation so a crash during startup is covered.
            reservation = json.loads(sys.stdin.buffer.readline(2048))
            if (set(reservation) != {'name', 'generation'}
                    or not re.fullmatch(r'luda-[0-9a-f]{32}', reservation['name'])
                    or not re.fullmatch(r'[0-9a-f]{32}', reservation['generation'])):
                raise ValueError('Invalid private device reservation')
            print('ready', flush=True)
            sys.stdin.buffer.read()
            if devices.generation() == reservation['generation']:
                found = {d['name']: d for d in devices.devices()}
                name = reservation['name']
                pointer, keyboard = found.get(name + ' pointer'), found.get(name + ' keyboard')
                if pointer and keyboard:
                    token = {**reservation, 'pointer': pointer['id'], 'keyboard': keyboard['id']}
        else:
            name = 'luda-' + secrets.token_hex(16)
            native.window_tokens([native.root])  # Initialize before any guarded validation.
            reservation = dict(name=name, generation=devices.generation())
            watchdog = subprocess.Popen([sys.executable, '-m', 'luda._private_input', 'watchdog'],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                        start_new_session=True)
            watchdog.stdin.write(json.dumps(reservation).encode() + b'\n')
            watchdog.stdin.flush()
            if (not select.select([watchdog.stdout], [], [], 1)[0]
                    or os.read(watchdog.stdout.fileno(), 64) != b'ready\n'):
                raise DesktopError('INPUT_UNAVAILABLE', 'Private input cleanup guardian did not start.')
            token = devices.create(name)
            print(json.dumps(token), flush=True)
            sys.stdin.buffer.read()  # Session exit or crash closes this pipe.
    except Exception:
        if not sys.argv[1:]:
            print(json.dumps({'error': 'Private input owner could not start.'}), flush=True)
    finally:
        if native:
            if token:
                Devices(native).remove(token)
            native.close()
        if watchdog:
            watchdog.stdin.close()
            watchdog.wait(timeout=2)
            watchdog.stdout.close()


if __name__ == '__main__':
    main()
