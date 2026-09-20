"""Prove ended private input ownership before binding a release connection."""
import ctypes as C
import os

from ._x11_helper import _NativeX11, _decode_window_token
from ._private_input import Devices, TOKEN_ENV, decode_token
from ._input_native import generation
from .common import DesktopError


def disconnect_injector(native, client):
    """Disconnect only the nonce-owned resource, including after device removal."""
    if not isinstance(client, dict) or type(client.get('xid')) is not int or not 0 < client['xid'] <= 0xffffffff:
        raise ValueError('Invalid injector identity')
    x = native.lib
    x.XGrabServer.argtypes = [C.c_void_p]
    x.XUngrabServer.argtypes = [C.c_void_p]
    x.XKillClient.argtypes = [C.c_void_p, C.c_ulong]
    x.XSync.argtypes = [C.c_void_p, C.c_int]
    x.XGrabServer(native.display)
    try:
        try:
            prop = native._property(client['xid'], '_LUDA_WINDOW_TOKEN', 9)
            if prop and _decode_window_token(*prop) == client.get('generation'):
                x.XKillClient(native.display, client['xid'])
                x.XSync(native.display, False)
        except DesktopError as exc:
            if exc.code != 'STALE_TARGET':
                raise
    finally:
        x.XUngrabServer(native.display)
        x.XSync(native.display, False)


def ended_ownership(request):
    """Return a no-release receipt only when the original ownership ended."""
    native = _NativeX11()
    try:
        if generation(native) != request['server_generation']:
            return {'released': False, 'session_changed': True, 'cleanup_skipped': True}
        # A removed master resets ClientPointer. Stop an old injector before
        # proving removal; never bind or emit a release on that reset connection.
        disconnect_injector(native, request['client'])
        token = decode_token(os.environ.get(TOKEN_ENV, ''))
        devices = Devices(native)
        if token['generation'] != request['server_generation']:
            raise DesktopError('SESSION_CHANGED', 'Cleanup identity does not match its original server.')
        names = {token['name'] + ' pointer', token['name'] + ' keyboard'}
        ids = {token['pointer'], token['keyboard']}
        # Renaming an existing master is not proof that its held state vanished.
        # Reused IDs are likewise ambiguous; keep cleanup blocked conservatively.
        if not any(device['name'] in names or device['id'] in ids for device in devices.devices()):
            return {'released': True, 'session_changed': False,
                    'cleanup_skipped': True, 'private_devices_removed': True}
        return None
    finally:
        native.close()
