"""Bounded X11 clipboard owner for an explicitly requested rich-editor route."""
import shutil
import subprocess
import time
from pathlib import Path
from .common import DesktopError, run, stop_process
from .storage import staged_payload
from .keyboard import send_chord, keyboard_capabilities


class Clipboard:
    def __init__(self, directory):
        self.directory=Path(directory)
        self.owner=None

    def preflight(self):
        if not shutil.which('xclip'):raise DesktopError('DEPENDENCY_MISSING','Clipboard transport requires xclip.')
        state=keyboard_capabilities()
        if not state.get('available'):raise DesktopError('KEYBOARD_UNAVAILABLE','Keyboard state is unavailable.')
        if state.get('latched_input'):raise DesktopError('UNSUPPORTED_INPUT_STATE','Clear latched input before clipboard typing.')
        if state.get('input_held'):raise DesktopError('INPUT_HELD','Release held input before clipboard typing.')

    def stage(self, text):
        payload=text.encode('utf-8')
        with staged_payload(self.directory,payload) as path:
            if self.owner:stop_process(self.owner)
            self.owner=subprocess.Popen(['xclip','-quiet','-selection','clipboard','-in',path],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            deadline=time.monotonic()+.8
            while True:
                if self.owner.poll() is not None:raise DesktopError('CLIPBOARD_FAILED','Clipboard owner exited; no paste shortcut sent.')
                try:
                    if run(['xclip','-selection','clipboard','-out'],timeout=.2,max_output_bytes=256001)==payload:break
                except DesktopError:pass
                if time.monotonic()>=deadline:raise DesktopError('CLIPBOARD_FAILED','Clipboard staging could not be verified; no paste shortcut sent.')
                time.sleep(.01)

    def verify(self, text):
        if not self.owner or self.owner.poll() is not None or run(['xclip','-selection','clipboard','-out'],timeout=.3,max_output_bytes=256001)!=text.encode('utf-8'):
            raise DesktopError('CLIPBOARD_CHANGED','Clipboard changed before paste; no shortcut sent.')

    def key(self, target, chord):
        return send_chord(chord,target['xid'],target_generation=target['generation'])

    def close(self):
        if self.owner:stop_process(self.owner)
        self.owner=None
