"""Pure validation shared by isolated native helpers and controller APIs."""
import re
from .common import DesktopError


def validate_position(position):
    if not isinstance(position,(list,tuple)) or len(position)!=2 or any(type(v) is not int or not 0<=v<=32767 for v in position):
        raise DesktopError('INVALID_ARGUMENT','Pointer position must contain two nonnegative X11 integer coordinates.')
    return list(position)


def validate_generation(value):
    if not isinstance(value,str) or not re.fullmatch('[0-9a-f]{32}',value):
        raise DesktopError('INVALID_ARGUMENT','Invalid X server generation.')
    return value


def validate_target_generation(target,value):
    if value is not None:
        if target is None:raise DesktopError('INVALID_ARGUMENT','A target generation requires a target window.')
        validate_generation(value)
    return value
