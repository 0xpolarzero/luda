"""Exact image-pixel bounds for the backend's floor-based pointer mapping."""


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
