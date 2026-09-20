"""EWMH no-initial-focus request for restoring an existing minimized window."""
from contextlib import contextmanager
import ctypes as C
import time
from .common import DesktopError


def map_without_focus(native, request):
    window, generation = request
    x, display = native.lib, native.display
    if native.window_tokens([window]).get(window) != generation:
        raise DesktopError('STALE_TARGET', 'Window changed before restoring.')
    proxy = native._property(window, '_NET_WM_USER_TIME_WINDOW', 1)
    targets = [window]
    if proxy is not None:
        kind, fmt, values, remaining = proxy
        if kind != 33 or fmt != 32 or remaining or len(values) != 1 or not values[0]:
            raise DesktopError('INVALID_PROPERTY', 'Invalid window user-time owner.')
        if values[0] != window:
            targets.append(values[0])
    identities = native.window_tokens(targets)
    if len(identities) != len(targets) or identities.get(window) != generation:
        raise DesktopError('STALE_TARGET', 'Window user-time owner disappeared.')
    atom = x.XInternAtom(display, b'_NET_WM_USER_TIME', False)
    native._property_atoms['_NET_WM_USER_TIME'] = atom
    hidden = x.XInternAtom(display, b'_NET_WM_STATE_HIDDEN', False)
    x.XDeleteProperty.argtypes = [C.c_void_p, C.c_ulong, C.c_ulong]
    x.XMapWindow.argtypes = [C.c_void_p, C.c_ulong]
    def write(target, value):
        data = (C.c_ulong * 1)(value)
        x.XChangeProperty(display, target, atom, 6, 32, 0,
                          C.cast(data, C.POINTER(C.c_ubyte)), 1)
    def same_identity(target):
        # Read only here: window_tokens takes its own server grab, which must
        # never release an enclosing guard before its protected mutation.
        prop = native._property(target, '_LUDA_WINDOW_TOKEN', 9)
        return prop == (31, 8, identities[target].encode('ascii'), 0)

    @contextmanager
    def guarded():
        x.XGrabServer(display)
        try:
            yield
        finally:
            x.XUngrabServer(display)
            x.XSync(display, False)

    changed, saved = [], {}
    try:
        with guarded():
            if (not all(same_identity(target) for target in targets)
                    or native._property(window, '_NET_WM_USER_TIME_WINDOW', 1) != proxy):
                raise DesktopError('STALE_TARGET', 'Window or user-time owner changed before restore.')
            for target in targets:
                prop = native._property(target, '_NET_WM_USER_TIME', 1)
                if prop is not None and (prop[0] != 6 or prop[1] != 32 or prop[3] or len(prop[2]) != 1):
                    raise DesktopError('INVALID_PROPERTY', 'Invalid window user-time value.')
                saved[target] = prop
            for target in targets:
                write(target, 0)
                changed.append(target)
            x.XMapWindow(display, window)
        deadline = time.monotonic() + 1
        while time.monotonic() < deadline:
            if not same_identity(window):
                raise DesktopError('STALE_TARGET', 'Window disappeared during restore.', effect='uncertain')
            state = native._property(window, '_NET_WM_STATE', 128)
            if state is not None and state[0] == 4 and state[1] == 32 and not state[3] and hidden not in state[2]:
                return {'effect': 'dispatched', 'verification': 'Mapped using the EWMH no-initial-focus request.'}
            time.sleep(.02)
        raise DesktopError('TIMEOUT', 'Window manager did not confirm restore.', effect='uncertain')
    finally:
        for target in changed:
            with guarded():
                # Do not overwrite a newer application timestamp or reused XID.
                try:
                    if not same_identity(target):
                        continue
                    if native._property(target, '_NET_WM_USER_TIME', 1) != (6, 32, [0], 0):
                        continue
                except DesktopError:
                    continue  # Destroyed or unreadable resources are not ours to repair.
                prop = saved[target]
                if prop is None:
                    x.XDeleteProperty(display, target, atom)
                else:
                    write(target, prop[2][0])
