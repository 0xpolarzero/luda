"""Honest capability declaration for the external X11/AT-SPI backend.

GTK built-in composition can exist without an IBus/Fcitx daemon and is absent
from committed AT-SPI Text. Engine presence, locale and text attributes are not
reliable composition-state queries. Never reset input methods to probe them.
"""


def composition_capability():
    return {
        'state': 'unknown',
        'detection_supported': False,
        'explicit_commit_supported': False,
        'explicit_cancel_supported': False,
        'conflicting_input_guard_supported': False,
        'text_verification_scope': 'Exposed text at readback; pending IME composition is not verified.',
        'guidance': 'If composition is active or suspected, preserve it and have it explicitly completed or cancelled before focus, selection, typing or paste. Do not send Escape or Return as automatic cleanup.',
    }
