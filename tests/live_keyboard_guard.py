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
            clear()
            result=send_chord('1',window['xid'],target_generation=window['window_id'].rsplit(':',1)[-1],count=20)
            wait(lambda:text()=='1'*20);assert result['dispatched_count']==20 and not oracle.pressed()
            clear();send_chord('Return',window['xid'],count=3);send_chord('Up',window['xid'],count=2);key('A')
            wait(lambda:text()=='\nA\n\n')
            clear();result=send_chord('shift+A',window['xid'],count=3)
            wait(lambda:text()=='AAA');assert result['dispatched_count']==3
            clear();repeat_cancel=threading.Event();repeat_errors=[]
            def repeat_case():
                try:
                    with operation_scope(cancelled=repeat_cancel):send_chord('1',window['xid'],count=20)
                except DesktopError as exc:repeat_errors.append(exc)
            repeating=threading.Thread(target=repeat_case);repeating.start();wait(lambda:len(text())>=3);repeat_cancel.set();repeating.join(4)
            assert not repeating.is_alive() and repeat_errors[0].code=='CANCELLED' and repeat_errors[0].effect=='uncertain'
            after=text();assert 3<=len(after)<20 and not oracle.pressed();time.sleep(.1);assert text()==after
            assert 'dispatched_count' not in repeat_errors[0].details
            rows.append('bounded-repeats-exact-text-navigation-full-chords-and-cancellation-no-replay')

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
            for layout in ('us','fr'):
                clear();subprocess.run(['setxkbmap',layout],check=True)
                for name in ('plus','minus','equal','comma','period','slash','semicolon'):
                    result=key(name);assert result['group_unchanged'] and result['locks_unchanged']
                wait(lambda:text()=='+-=,./;')
                for name,expected in (('plus',43),('minus',45),('slash',47)):
                    before=len(json.loads((output/'state.json').read_text())['events'])
                    key('ctrl+'+name)
                    def delivered():
                        events=json.loads((output/'state.json').read_text())['events'][before:]
                        return any(e['keyval']==expected and e['state']&4 and 'KEY_PRESS' in e['kind'] for e in events)
                    wait(delivered);assert not oracle.pressed()
            rows.append('named-punctuation-and-control-shortcuts-us-french-independent-events')
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
            # Stop both companion and injector after an independent real press.
            # Hold the recovery SIGCONT briefly to prove the pending gate stays
            # closed before the same companion is allowed to finish cleanup.
            from unittest.mock import patch
            from luda import keyboard
            previous=(keyboard._retain_recovery,keyboard._release_recovery)
            retained=[];released=threading.Event();resuming=threading.Event();allow_resume=threading.Event();pending_errors=[]
            original_kill=os.kill
            def controlled_resume(pid,operation):
                if operation==signal.SIGCONT:
                    resuming.set();allow_resume.wait(5)
                return original_kill(pid,operation)
            def pending_case():
                try:
                    with operation_scope(timeout=14):send_chord('ctrl+shift+alt+F12',window['xid'])
                except DesktopError as exc:pending_errors.append(exc)
            def release(token):released.set()
            keyboard.set_recovery_hooks(retained.append,release)
            try:
                with patch('luda.keyboard.os.kill',side_effect=controlled_resume):
                    pending_thread=threading.Thread(target=pending_case);pending_thread.start()
                    wait(lambda:oracle.code('Control_L') in oracle.pressed())
                    guards=[pid for pid in descendants(os.getpid()) if b'luda._keyboard_guard' in Path(f'/proc/{pid}/cmdline').read_bytes()]
                    assert len(guards)==1,guards
                    injectors=descendants(guards[0]);assert len(injectors)==1,injectors
                    original_kill(injectors[0],signal.SIGSTOP);original_kill(guards[0],signal.SIGSTOP)
                    pending_thread.join(13)
                    assert not pending_thread.is_alive()
                    assert pending_errors and pending_errors[0].code=='KEYBOARD_CLEANUP_PENDING',pending_errors
                    assert pending_errors[0].effect=='uncertain' and len(retained)==1
                    assert resuming.wait(1) and not released.is_set()
                    try:send_chord('Return',window['xid']);raise AssertionError('new input passed pending cleanup')
                    except DesktopError as exc:assert exc.code=='BUSY',exc.code
                    assert oracle.code('Control_L') in oracle.pressed()
                    allow_resume.set();assert released.wait(4)
                    wait(lambda:not oracle.pressed())
                    keyboard.keyboard_recovery_checkpoint()
            finally:
                allow_resume.set();keyboard.set_recovery_hooks(*previous)
            rows.append('stopped-guardian-pending-gate-blocks-input-until-verified-recovery')
            # Inject a guardian selector fault after the armed worker message,
            # then independently prove that exception cleanup still releases.
            fault_script="""import selectors,time
original=selectors.DefaultSelector
class FaultSelector(original):
 def select(self,timeout=None):
  if getattr(self,'seen_worker',False):
   time.sleep(.1)
   raise OSError('synthetic selector fault')
  events=super().select(timeout)
  if any(key.data=='worker' for key,mask in events):self.seen_worker=True
  return events
selectors.DefaultSelector=FaultSelector
from luda._keyboard_guard import main
main()
"""
            plan=subprocess.check_output([sys.executable,'-m','luda._keyboard_native','plan'],input=json.dumps({'chord':'ctrl+shift+alt+F12','target':window['xid']}).encode()+b'\n')
            faulty=subprocess.Popen([sys.executable,'-c',fault_script],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL)
            try:
                faulty.stdin.write(plan);faulty.stdin.flush()
                wait(lambda:oracle.code('Control_L') in oracle.pressed())
                injectors=descendants(faulty.pid);assert len(injectors)==1,injectors
                os.kill(injectors[0],signal.SIGSTOP)
                wait(lambda:not oracle.pressed(),3)
                assert select.select([faulty.stdout],[],[],3)[0]
                response=json.loads(faulty.stdout.readline())
                assert response['code']=='KEYBOARD_UNAVAILABLE' and response['cleanup_verified'],response
                faulty.wait(timeout=3)
            finally:
                faulty.stdin.close();faulty.stdout.close()
                if faulty.poll() is None:faulty.kill();faulty.wait(timeout=2)
            rows.append('guardian-resource-fault-after-arming-cleans-owned-keys')
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
    with tempfile.TemporaryDirectory(prefix='luda-private-keyboard-session-') as directory:
        env=dict(os.environ)
        for key,name in (('XDG_CONFIG_HOME','config'),('XDG_DATA_HOME','data'),('XDG_CACHE_HOME','cache'),('XDG_RUNTIME_DIR','runtime')):
            path=Path(directory)/name;path.mkdir(mode=0o700);env[key]=str(path)
        env['XDG_CONFIG_DIRS']=env['XDG_CONFIG_HOME']
        result=subprocess.run(['xvfb-run','-a','-s','-screen 0 1000x750x24 -nolisten tcp','dbus-run-session','--',sys.executable,str(Path(__file__).resolve()),'--child'],env=env,timeout=45)
    raise SystemExit(result.returncode)

if __name__=='__main__':main()
