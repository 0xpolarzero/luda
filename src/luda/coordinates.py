"""Exact image-pixel bounds for the backend's floor-based pointer mapping."""
import hashlib
import json


def image_bounds(bounds, native_size, image_size):
    """Return integer image positions mapping into a native half-open rectangle.

    Each image index i maps to floor(i * native / image). Thus the first
    permitted index is ceil(left * image / native), and the exclusive end is
    ceil(right * image / native). Integer arithmetic handles negative origins
    without floating-point boundary drift. No integer positions means None,
    including visible native slivers omitted by downsampling.
    """
    nw, nh = native_size
    iw, ih = image_size
    if min(nw, nh, iw, ih) <= 0:
        raise ValueError('Native and image dimensions must be positive.')
    if bounds['width'] <= 0 or bounds['height'] <= 0:
        return None

    def interval(start, length, native, image):
        left = max(0, min(image, (start * image + native - 1) // native))
        right = max(0, min(image, ((start + length) * image + native - 1) // native))
        return left, right

    left, right = interval(bounds['x'], bounds['width'], nw, iw)
    top, bottom = interval(bounds['y'], bounds['height'], nh, ih)
    if left >= right or top >= bottom:
        return None
    return {'x': left, 'y': top, 'width': right - left, 'height': bottom - top}


def topology_summary(topology, image_size=None):
    """Agent-facing layout; full native metadata stays in snapshot validation."""
    randr=topology['randr'];root=topology['root']
    modern=tuple(randr['version']) >= (1,5)
    regions=randr['monitors'] if modern else [c for c in randr['crtcs'] if c['mode'] and c['width'] and c['height']]
    monitors=[]
    for region in regions:
        bounds={key:region[key] for key in ('x','y','width','height')}
        row={'bounds':bounds,'primary':bool(region['primary']) if modern else None}
        if image_size is not None:row['image_bounds']=image_bounds(bounds,(root['width'],root['height']),image_size)
        monitors.append(row)
    return {'layout_id':hashlib.sha256(json.dumps(topology,sort_keys=True,separators=(',',':')).encode()).hexdigest(),
            'root':root,'monitor_source':'RandR logical monitors' if modern else 'active display controllers',
            'monitors':monitors,'bounds_coordinate_space':'native_x11_root_pixels'}
