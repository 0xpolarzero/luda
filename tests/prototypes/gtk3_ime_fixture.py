"""Private fixture: actual key input plus explicitly synthetic lifecycle cases."""
import ctypes
import gc
import json
import os
from pathlib import Path
import subprocess
import sys
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, GLib

out = Path(sys.argv[1]); mode = sys.argv[2]; module = sys.argv[3]
window = Gtk.Window(title='Luda startup IME observer')
entry = Gtk.Entry(); window.add(entry); window.show_all(); entry.grab_focus()
state = {'preedit_nonempty': False, 'preedit_events': 0, 'committed_unchanged': True}
def publish():
    state['committed_unchanged'] = entry.get_text() == ''
    out.write_text(json.dumps(state))
def preedit(_entry, text):
    state['preedit_nonempty'] = bool(text)
    state['preedit_events'] += 1
    publish()
entry.connect('preedit-changed', preedit)
publish()

def keys(*args):
    subprocess.run(['xdotool', 'key', '--clearmodifiers', *args], check=True, timeout=3)
def begin():
    # Owned Xvfb, owned window. This is a hook prototype, not a Luda input test.
    xid = str(window.get_window().get_xid())
    subprocess.run(['xdotool', 'windowfocus', '--sync', xid], check=True, timeout=3)
    keys('ctrl+shift+u', '3', '0', '6', 'b')
    GLib.timeout_add(250, after_preedit)
    return False

def after_preedit():
    assert state['preedit_nonempty']
    if mode == 'late':
        library = ctypes.CDLL(module)
        library.gtk_module_init(None, None)
        # No replay on attach. Retain active independently, then end normally.
        state['late_active_before_attach'] = True
        publish()
    GLib.timeout_add(250, end)
    return False

def end():
    keys('Escape')
    GLib.timeout_add(250, lifecycle)
    return False

def lifecycle():
    assert not state['preedit_nonempty'] and state['committed_unchanged']
    # Controlled signal contracts, NOT claims about a particular real engine.
    context = Gtk.IMContextSimple()
    context.emit('preedit-changed') # First signal conveys no lifecycle history.
    context.emit('preedit-start')
    context.emit('preedit-changed') # Empty getter isn't consulted by observer.
    context.emit('preedit-end')
    del context; gc.collect()
    replacement = Gtk.IMContextSimple()
    replacement.emit('preedit-start')
    del replacement; gc.collect() # Destruction without preedit-end.
    state['synthetic_lifecycle_completed'] = True
    publish()
    window.destroy(); Gtk.main_quit()
    return False

GLib.timeout_add(250, begin)
GLib.timeout_add_seconds(8, lambda: os._exit(9))
Gtk.main()
