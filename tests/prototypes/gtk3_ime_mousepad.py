"""Actual stock Mousepad module loading, entirely inside the runner's private X11."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import gi
gi.require_version('Gtk', '3.0')
from gi.repository import Gtk, Gdk, GObject
out = Path(sys.argv[1]); module = sys.argv[2]
fd = int(os.environ['LUDA_IME_PROBE_FD'])
file = out / 'owned.txt'; file.write_text('BASE')
env = dict(os.environ, GTK3_MODULES=module)
process = subprocess.Popen(['mousepad', '--disable-server', str(file)], env=env, pass_fds=(fd,))
def run(*args):
    return subprocess.run(['xdotool', *args], check=True, capture_output=True, text=True, timeout=3).stdout.strip()
try:
    deadline = time.monotonic() + 6
    while True:
        try:
            windows = run('search', '--onlyvisible', '--pid', str(process.pid)).splitlines()
            if windows: break
        except subprocess.CalledProcessError: pass
        assert time.monotonic() < deadline, 'Mousepad window did not appear'
        time.sleep(.05)
    run('windowfocus', '--sync', windows[-1])
    run('key', '--clearmodifiers', 'ctrl+End', 'ctrl+shift+u', '3', '0', '6', 'b')
    time.sleep(.3)
    root = Gdk.get_default_root_window()
    Gdk.pixbuf_get_from_window(root, 0, 0, root.get_width(), root.get_height()).savev(str(out/'mousepad-active.png'), 'png', [], [])
    run('key', '--clearmodifiers', 'Escape')
    time.sleep(.2)
    assert file.read_text() == 'BASE'
    # Inspect only public metadata; there is no client-widget/property binding here.
    properties = [prop.name for prop in GObject.list_properties(Gtk.IMContext)]
    (out/'mousepad.oracle.json').write_text(json.dumps({'file_unchanged':True, 'context_public_properties':properties,
        'version': subprocess.check_output(['mousepad','--version'], text=True).splitlines()[0]}))
finally:
    process.terminate()
    try: process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        process.kill(); process.wait(timeout=3)
