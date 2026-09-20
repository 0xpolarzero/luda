"""Independent key-state oracle on an owned private Xvfb display only."""
import ctypes as C
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import tempfile
import threading
import time
from luda.common import DesktopError, operation_scope
from luda.desktop import Desktop
from luda.keyboard import send_chord
ROOT=Path(__file__).resolve().parents[1]


class Oracle:
    def __init__(self):
        self.x=C.CDLL('libX11.so.6');x=self.x
        x.XOpenDisplay.argtypes=[C.c_char_p];x.XOpenDisplay.restype=C.c_void_p
        self.d=x.XOpenDisplay(None)
        x.XQueryKeymap.argtypes=[C.c_void_p,C.c_void_p]
        x.XStringToKeysym.argtypes=[C.c_char_p];x.XStringToKeysym.restype=C.c_ulong
        x.XKeysymToKeycode.argtypes=[C.c_void_p,C.c_ulong];x.XKeysymToKeycode.restype=C.c_ubyte
        x.XDefaultRootWindow.argtypes=[C.c_void_p];x.XDefaultRootWindow.restype=C.c_ulong
        x.XQueryPointer.argtypes=[C.c_void_p,C.c_ulong,C.POINTER(C.c_ulong),C.POINTER(C.c_ulong)]+[C.POINTER(C.c_int)]*4+[C.POINTER(C.c_uint)]
        x.XkbLockGroup.argtypes=[C.c_void_p,C.c_uint,C.c_uint];x.XSync.argtypes=[C.c_void_p,C.c_int]
        x.XCloseDisplay.argtypes=[C.c_void_p]
    def pressed(self):
        value=(C.c_ubyte*32)();self.x.XQueryKeymap(self.d,value)
        return {k for k in range(8,256) if value[k//8]&(1<<(k%8))}
    def code(self,name):return self.x.XKeysymToKeycode(self.d,self.x.XStringToKeysym(name.encode()))
    def buttons(self):
        root,child=C.c_ulong(),C.c_ulong();coords=[C.c_int() for _ in range(4)];mask=C.c_uint()
        self.x.XQueryPointer(self.d,self.x.XDefaultRootWindow(self.d),C.byref(root),C.byref(child),*[C.byref(v) for v in coords],C.byref(mask))
        return mask.value&0x1f00
    def group(self,group):self.x.XkbLockGroup(self.d,0x100,group);self.x.XSync(self.d,False)
    def close(self):self.x.XCloseDisplay(self.d)


def wait(predicate,timeout=3):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if predicate():return
        time.sleep(.001)
    raise AssertionError('Independent oracle deadline exceeded')


def descendants(pid):
    result=[]
    for path in Path('/proc').iterdir():
        if not path.name.isdigit():continue
        try:
            fields=(path/'stat').read_text().rsplit(')',1)[1].split()
            if int(fields[1])==pid:result.append(int(path.name))
        except (OSError,ValueError):pass
    return result


def run_child():
    rows=[]
    with tempfile.TemporaryDirectory(prefix='luda-keyboard-app-') as directory:
        output=Path(directory)
        wm=subprocess.Popen(['xfwm4','--compositor=off'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        fixture=None;desktop=None;oracle=None
        try:
            wait(lambda:subprocess.run(['wmctrl','-m'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0)
            fixture=subprocess.Popen(['/usr/bin/python3',str(ROOT/'tests/keyboard_fixture.py'),directory],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            desktop=Desktop();oracle=Oracle()
            found=[]
            wait(lambda:bool(found.extend(w for w in desktop.list_windows() if w['pid']==fixture.pid) or found),5)
            window=found[0];desktop.activate(window['window_id'])
            wait(lambda:(output/'state.json').exists())
            def text():return json.loads((output/'state.json').read_text())['text']
            def key(chord):return desktop.key(window['window_id'],chord)
            def clear():key('ctrl+a');key('BackSpace')
            for chord in ('A','a','1'):
                result=key(chord);assert result['group_unchanged'] and result['locks_unchanged']
            wait(lambda:text()=='Aa1')
            rows.append('bare-uppercase-lowercase-digit-readback')
            subprocess.run(['xdotool','keydown','Shift_L'],check=True)
            held=oracle.pressed();assert oracle.code('Shift_L') in held
            try:
                try:key('ctrl+s');raise AssertionError('held key accepted')
                except DesktopError as exc:assert exc.code=='INPUT_HELD',exc.code
                assert oracle.pressed()==held
            finally:subprocess.run(['xdotool','keyup','Shift_L'],check=True)
            subprocess.run(['xdotool','mousedown','1'],check=True)
            held_button=oracle.buttons();assert held_button
            try:
                try:key('Return');raise AssertionError('held button accepted')
                except DesktopError as exc:assert exc.code=='INPUT_HELD',exc.code
                assert oracle.buttons()==held_button
            finally:subprocess.run(['xdotool','mouseup','1'],check=True)
            rows.append('held-key-and-button-refused-without-clearing')
            clear();subprocess.run(['xdotool','key','Caps_Lock'],check=True)
            for chord in ('A','a','1'):
                result=key(chord);assert result['locks_unchanged']
            wait(lambda:text()=='Aa1')
            assert 'Caps Lock:   on' in subprocess.check_output(['xset','q'],text=True)
            subprocess.run(['xdotool','key','Caps_Lock'],check=True)
            rows.append('caps-lock-preserved-with-case-readback')
            clear();subprocess.run(['xdotool','key','Num_Lock'],check=True)
            result=key('1');assert result['locks_unchanged']
            wait(lambda:text()=='1')
            import re
            assert re.search(r'Num Lock:\s+on',subprocess.check_output(['xset','q'],text=True))
            subprocess.run(['xdotool','key','Num_Lock'],check=True)
            rows.append('num-lock-preserved-with-digit-readback')
            clear();subprocess.run(['setxkbmap','fr'],check=True)
            key('A');key('1');wait(lambda:text()=='A1')
            rows.append('french-layout-uppercase-and-shifted-digit')
            subprocess.run(['setxkbmap','-layout','us,ru'],check=True);oracle.group(1)
            try:key('a');raise AssertionError('unsupported current-group symbol accepted')
            except DesktopError as exc:assert exc.code=='UNSUPPORTED_KEYMAP',exc.code
            result=key('Return');assert result['group_unchanged']
            oracle.group(0);subprocess.run(['setxkbmap','us'],check=True)
            rows.append('current-group-preserved-and-unmapped-symbol-refused')
            # Kill controller with its owned injection child deliberately stopped
            # after independent observation of a real Control key press.
            controller=subprocess.Popen([sys.executable,'-c','from luda.keyboard import send_chord;send_chord("ctrl+shift+alt+F12",'+str(window['xid'])+')'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            try:
                control=oracle.code('Control_L');wait(lambda:control in oracle.pressed())
                guards=descendants(controller.pid);assert len(guards)==1,guards
                workers=descendants(guards[0]);assert len(workers)==1,workers
                os.kill(workers[0],signal.SIGSTOP)
                # A new unrelated held key must survive targeted cleanup.
                subprocess.run(['xdotool','keydown','b'],check=True)
                unrelated=oracle.code('b')
                controller.kill();controller.wait(timeout=2)
                wait(lambda:oracle.pressed()=={unrelated},3)
                subprocess.run(['xdotool','keyup','b'],check=True)
                wait(lambda:not oracle.pressed(),3)
                wait(lambda:not Path('/proc',str(workers[0])).exists(),3)
            finally:
                if controller.poll() is None:controller.kill();controller.wait(timeout=2)
            rows.append('controller-death-kills-stopped-injector-before-owned-release')
            cancellation=threading.Event();errors=[]
            def cancel_case():
                try:
                    with operation_scope(cancelled=cancellation):send_chord('ctrl+shift+alt+F12',window['xid'])
                except DesktopError as exc:errors.append(exc)
            worker=threading.Thread(target=cancel_case);worker.start()
            wait(lambda:oracle.code('Control_L') in oracle.pressed())
            cancellation.set();worker.join(4)
            assert not worker.is_alive()
            assert errors and errors[0].code=='CANCELLED' and errors[0].effect=='uncertain',errors
            wait(lambda:not oracle.pressed())
            rows.append('midchord-cancellation-releases-owned-keys')
            assert not oracle.buttons()
        finally:
            if oracle:oracle.close()
            if desktop:desktop.close()
            if fixture and fixture.poll() is None:fixture.terminate();fixture.wait(timeout=3)
            if wm.poll() is None:wm.terminate();wm.wait(timeout=3)
    print(json.dumps({'passed':rows},indent=2))


def main():
    if '--child' in sys.argv:return run_child()
    # The external command creates both display and bus and bounds the entire
    # suite. No shared display input or application is touched.
    result=subprocess.run(['xvfb-run','-a','-s','-screen 0 1000x750x24 -nolisten tcp','dbus-run-session','--',sys.executable,str(Path(__file__).resolve()),'--child'],timeout=45)
    raise SystemExit(result.returncode)

if __name__=='__main__':main()
