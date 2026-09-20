"""Read-only X11 oracles for windows owned by a live test fixture."""
import re
import subprocess


def application_target(windows, main_id):
    """Return the deepest mapped owned transient, or its mapped main window.

    MPX input can leave the WM's core active-window hint empty. Dialog mapping
    and transient relationships identify the application's actual interaction
    surface independently of that hint; callers still verify file/PTY effects.
    """
    mapped = {}
    parents = {}
    for window in windows:
        info = subprocess.run(['xwininfo', '-id', str(window['xid'])], capture_output=True, text=True)
        if info.returncode or 'Map State: IsViewable' not in info.stdout:
            continue
        mapped[window['xid']] = window
        prop = subprocess.run(['xprop', '-id', str(window['xid']), 'WM_TRANSIENT_FOR'], capture_output=True, text=True)
        match = re.search(r'window id # (0x[0-9a-fA-F]+)', prop.stdout)
        if match:
            parents[window['xid']] = int(match.group(1), 16)
    root = next((xid for xid, window in mapped.items() if window['window_id'] == main_id), None)
    if root is None:
        return None
    def depth(xid):
        seen = set()
        while xid in parents and xid not in seen:
            seen.add(xid)
            xid = parents[xid]
        return len(seen) if seen or xid == root else -1
    # File managers can attach confirmation dialogs to a separate progress
    # window rather than the main window; all candidates belong to our PID.
    ranked = sorted(((depth(xid), xid) for xid in mapped), reverse=True)
    if len(ranked) > 1 and ranked[0][0] == ranked[1][0]:
        return None  # Ambiguous siblings must not silently choose a dialog.
    return mapped[ranked[0][1]]['window_id']
