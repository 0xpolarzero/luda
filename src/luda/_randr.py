"""Bounded RandR metadata on the helper's existing native connection.

ABI: Xrandr.h from libXrandr 1.5.2; fixed-point transforms use signed int32.
No output names, EDID, connector properties or display configuration writes.
"""
import ctypes as C
from .common import DesktopError


class Resources(C.Structure):
    _fields_ = [('timestamp', C.c_ulong), ('configTimestamp', C.c_ulong),
                ('ncrtc', C.c_int), ('crtcs', C.POINTER(C.c_ulong)),
                ('noutput', C.c_int), ('outputs', C.POINTER(C.c_ulong)),
                ('nmode', C.c_int), ('modes', C.c_void_p)]


class Crtc(C.Structure):
    _fields_ = [('timestamp', C.c_ulong), ('x', C.c_int), ('y', C.c_int),
                ('width', C.c_uint), ('height', C.c_uint), ('mode', C.c_ulong),
                ('rotation', C.c_ushort), ('noutput', C.c_int),
                ('outputs', C.POINTER(C.c_ulong)), ('rotations', C.c_ushort),
                ('npossible', C.c_int), ('possible', C.POINTER(C.c_ulong))]


class Transform(C.Structure):
    _fields_ = [('pending', C.c_int32 * 9), ('pendingFilter', C.c_void_p),
                ('pendingNparams', C.c_int), ('pendingParams', C.c_void_p),
                ('current', C.c_int32 * 9), ('currentFilter', C.c_void_p),
                ('currentNparams', C.c_int), ('currentParams', C.c_void_p)]


class Panning(C.Structure):
    _fields_ = [('timestamp', C.c_ulong)] + [(name, C.c_uint) for name in
        ('left', 'top', 'width', 'height', 'track_left', 'track_top', 'track_width', 'track_height')] + [
        (name, C.c_int) for name in ('border_left', 'border_top', 'border_right', 'border_bottom')]


class Monitor(C.Structure):
    _fields_ = [('name', C.c_ulong)] + [(name, C.c_int) for name in
        ('primary', 'automatic', 'noutput', 'x', 'y', 'width', 'height', 'mwidth', 'mheight')] + [
        ('outputs', C.POINTER(C.c_ulong))]


IDENTITY = [65536, 0, 0, 0, 65536, 0, 0, 0, 65536]


def bounded_values(pointer, count, limit=64):
    if not 0 <= count <= limit or (count and not pointer):
        raise DesktopError('TOPOLOGY_UNAVAILABLE', 'Display topology exceeds the bounded metadata contract.')
    return list(pointer[:count]) if count else []


def read_topology(native):
    try:
        lib = C.CDLL('libXrandr.so.2')
    except OSError:
        raise DesktopError('DEPENDENCY_MISSING', 'Display topology requires libxrandr2.')
    signatures = {
        'XRRQueryVersion': ([C.c_void_p, C.POINTER(C.c_int), C.POINTER(C.c_int)], C.c_int),
        'XRRGetScreenResourcesCurrent': ([C.c_void_p, C.c_ulong], C.POINTER(Resources)),
        'XRRFreeScreenResources': ([C.POINTER(Resources)], None),
        'XRRGetCrtcInfo': ([C.c_void_p, C.POINTER(Resources), C.c_ulong], C.POINTER(Crtc)),
        'XRRFreeCrtcInfo': ([C.POINTER(Crtc)], None),
        'XRRGetCrtcTransform': ([C.c_void_p, C.c_ulong, C.POINTER(C.POINTER(Transform))], C.c_int),
        'XRRGetPanning': ([C.c_void_p, C.POINTER(Resources), C.c_ulong], C.POINTER(Panning)),
        'XRRFreePanning': ([C.POINTER(Panning)], None),
        'XRRGetMonitors': ([C.c_void_p, C.c_ulong, C.c_int, C.POINTER(C.c_int)], C.POINTER(Monitor)),
        'XRRFreeMonitors': ([C.POINTER(Monitor)], None),
    }
    for name, (args, result) in signatures.items():
        function = getattr(lib, name)
        function.argtypes = args
        function.restype = result
    major, minor = C.c_int(), C.c_int()
    if not lib.XRRQueryVersion(native.display, C.byref(major), C.byref(minor)) or (major.value, minor.value) < (1, 3):
        raise DesktopError('TOPOLOGY_UNAVAILABLE', 'RandR 1.3 or newer is required to validate display layout.')
    resources = lib.XRRGetScreenResourcesCurrent(native.display, native.root)
    if not resources:
        raise DesktopError('TOPOLOGY_UNAVAILABLE', 'Cannot read current display resources.')
    try:
        resource = resources.contents
        result = {'version': [major.value, minor.value],
                  'timestamp': resource.timestamp, 'config_timestamp': resource.configTimestamp,
                  'outputs': sorted(bounded_values(resource.outputs, resource.noutput)),
                  'crtcs': [], 'monitors': []}
        for xid in sorted(bounded_values(resource.crtcs, resource.ncrtc)):
            info = lib.XRRGetCrtcInfo(native.display, resources, xid)
            if not info:
                raise DesktopError('DESKTOP_CHANGED', 'Display controller changed during observation.')
            try:
                value = info.contents
                row = {'id': xid, 'timestamp': value.timestamp, 'x': value.x, 'y': value.y,
                       'width': value.width, 'height': value.height, 'mode': value.mode,
                       'rotation': value.rotation, 'outputs': sorted(bounded_values(value.outputs, value.noutput))}
            finally:
                lib.XRRFreeCrtcInfo(info)
            transform = C.POINTER(Transform)()
            try:
                if not lib.XRRGetCrtcTransform(native.display, xid, C.byref(transform)) or not transform:
                    raise DesktopError('TOPOLOGY_UNAVAILABLE', 'Cannot read display transform.')
                row['transform'] = list(transform.contents.current)
            finally:
                if transform:
                    native.lib.XFree.argtypes = [C.c_void_p]
                    native.lib.XFree(transform)
            pan = lib.XRRGetPanning(native.display, resources, xid)
            try:
                # Some virtual drivers have no panning interface. Distinguish
                # absence from an enabled panning viewport, never synthesize one.
                row['panning'] = {name: getattr(pan.contents, name) for name, _ in Panning._fields_} if pan else None
            finally:
                if pan: lib.XRRFreePanning(pan)
            result['crtcs'].append(row)
        if (major.value, minor.value) >= (1, 5):
            count = C.c_int()
            monitors = lib.XRRGetMonitors(native.display, native.root, False, C.byref(count))
            try:
                for value in bounded_values(monitors, count.value):
                    result['monitors'].append({name: getattr(value, name) for name, _ in Monitor._fields_ if name not in ('outputs', 'noutput')})
                    result['monitors'][-1]['outputs'] = sorted(bounded_values(value.outputs, value.noutput))
                result['monitors'].sort(key=lambda row: row['name'])
            finally:
                if monitors: lib.XRRFreeMonitors(monitors)
        return result
    finally:
        lib.XRRFreeScreenResources(resources)
