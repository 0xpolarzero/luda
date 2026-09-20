"""Read-only native identity preflight for directly addressed browser input."""
from .common import DesktopError
from .keyboard import validate_chord
from .x11 import X11


class NativeInput:
    def validate_target(self,target):
        if not isinstance(target,dict):
            raise DesktopError('STALE_TARGET','Browser native target is unavailable.')
        actual=X11().window_tokens([target['xid']]).get(target['xid'])
        if actual!=target.get('generation'):
            raise DesktopError('STALE_TARGET','Browser native window identity changed.')

    def focus(self,target):
        # DOM focus and CDP focus emulation do not need a desktop input device.
        self.validate_target(target)

    def prepare_key(self,target,chord):
        validate_chord(chord)
        self.validate_target(target)
        # The worker rechecks DOM focus and composition after this bounded read.
        # CDP keys do not use the desktop keymap or physical held-key state.
