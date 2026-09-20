"""Restart an owned X server at the exact same DISPLAY and authority path."""
import argparse
import ctypes as C
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import tempfile
import time
from live_keyboard_guard import Oracle,wait,descendants
from luda.common import environment_scope,DesktopError
from luda.pointer_input import move_pointer
from luda.input_guard import HeldPointer
from luda import keyboard


def stop_owned_server(server, timeout=3):
    """Final fixture cleanup only; never retry assertions or affect other PIDs."""
    escalated = False
    if server.poll() is None:
        server.terminate()
        try:
            server.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            escalated = True
            server.kill()
            # A failure to reap still fails the test; no process is abandoned.
            server.wait(timeout=timeout)
    return {'term_to_kill_escalated': escalated, 'returncode': server.returncode}


def main(stall_cleanup=False):
    server=None;oracle=None;key_guard=None;mouse_guard=None;mouse_writer=None
    with tempfile.TemporaryDirectory(prefix='luda-input-generation-') as directory:
        base=Path(directory);authority=base/'authority';authority.touch(mode=0o600)
        reader,writer=os.pipe()
        server=subprocess.Popen(['Xvfb','-displayfd',str(writer),'-screen','0','800x600x24','-nolisten','tcp','-ac','-auth',str(authority)],pass_fds=(writer,),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        os.close(writer)
        assert select.select([reader],[],[],5)[0]
        number=os.read(reader,32).decode().strip();os.close(reader)
        env=dict(os.environ,DISPLAY=':'+number,XAUTHORITY=str(authority))
        original_env=dict(os.environ)
        def native(request):
            return json.loads(subprocess.check_output([sys.executable,'-m','luda._input_native'],input=json.dumps(request).encode()+b'\n',env=env,timeout=3))
        def command(*args):subprocess.run(args,env=env,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            os.environ.update(DISPLAY=env['DISPLAY'],XAUTHORITY=env['XAUTHORITY'])
            oracle=Oracle();x=oracle.x
            x.XCreateSimpleWindow.argtypes=[C.c_void_p,C.c_ulong,C.c_int,C.c_int,C.c_uint,C.c_uint,C.c_uint,C.c_ulong,C.c_ulong];x.XCreateSimpleWindow.restype=C.c_ulong
            window=x.XCreateSimpleWindow(oracle.d,x.XDefaultRootWindow(oracle.d),0,0,200,100,0,0,0);x.XSync(oracle.d,False)
            command('xprop','-root','-f','_NET_ACTIVE_WINDOW','32x','-set','_NET_ACTIVE_WINDOW',hex(window))
            plan=json.loads(subprocess.check_output([sys.executable,'-m','luda._keyboard_native','plan'],input=json.dumps({'chord':'ctrl+shift+alt+F12','target':window}).encode()+b'\n',env=env,timeout=3))
            assert 'server_generation' in plan,plan
            old_generation=plan['server_generation']
            key_guard=subprocess.Popen([sys.executable,'-m','luda._keyboard_guard'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env=env)
            key_guard.stdin.write(json.dumps(plan).encode()+b'\n');key_guard.stdin.flush()
            wait(lambda:oracle.code('Control_L') in oracle.pressed())
            children=descendants(key_guard.pid);assert len(children)==1
            os.kill(children[0],signal.SIGSTOP);os.kill(key_guard.pid,signal.SIGSTOP)
            # Clear only this stopped test injector's own keys so the held
            # pointer planner can independently enforce its preheld-input rule.
            command('xdotool','keyup','Control_L','Shift_L','Alt_L','F12')
            mouse_plan=json.loads(subprocess.check_output([sys.executable,'-m','luda._pointer_native','plan'],input=json.dumps({'button':'1','count':1,'target':None,'hold':True}).encode()+b'\n',env=env,timeout=3))
            mouse_guard=subprocess.Popen([sys.executable,'-m','luda._keyboard_guard'],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,env=env)
            mouse_guard.stdin.write(json.dumps(mouse_plan).encode()+b'\n');mouse_guard.stdin.flush()
            assert json.loads(mouse_guard.stdout.readline())['held']
            mouse_children=descendants(mouse_guard.pid);assert len(mouse_children)==1
            os.kill(mouse_children[0],signal.SIGSTOP);os.kill(mouse_guard.pid,signal.SIGSTOP)
            assert oracle.buttons()
            oracle.close();oracle=None
            server.terminate();server.wait(timeout=3)
            server=subprocess.Popen(['Xvfb',env['DISPLAY'],'-screen','0','800x600x24','-nolisten','tcp','-ac','-auth',str(authority)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            wait(lambda:subprocess.run(['xdpyinfo'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0)
            oracle=Oracle();new_generation=native({'operation':'generation'})['server_generation'];assert new_generation!=old_generation
            oracle.x.XCreateSimpleWindow.argtypes=[C.c_void_p,C.c_ulong,C.c_int,C.c_int,C.c_uint,C.c_uint,C.c_uint,C.c_ulong,C.c_ulong];oracle.x.XCreateSimpleWindow.restype=C.c_ulong
            new_window=oracle.x.XCreateSimpleWindow(oracle.d,oracle.x.XDefaultRootWindow(oracle.d),0,0,200,100,0,0,0)
            oracle.x.XSync(oracle.d,False)
            assert new_window==window,'replacement must reuse numeric target XID'
            command('xprop','-root','-f','_NET_ACTIVE_WINDOW','32x','-set','_NET_ACTIVE_WINDOW',hex(new_window))
            refused=json.loads(subprocess.check_output([sys.executable,'-m','luda._keyboard_native','plan'],input=json.dumps({'chord':'Return','target':new_window,'target_generation':plan['target_generation']}).encode()+b'\n',env=env,timeout=3))
            assert refused['code']=='STALE_TARGET' and refused['effect']=='none',refused
            command('xdotool','keydown','Control_L');command('xdotool','mousedown','1')
            command('xdotool','mousemove','321','234')
            def pointer_position():
                root,child=C.c_ulong(),C.c_ulong();coords=[C.c_int() for _ in range(4)];mask=C.c_uint()
                oracle.x.XQueryPointer(oracle.d,oracle.x.XDefaultRootWindow(oracle.d),C.byref(root),C.byref(child),*[C.byref(v) for v in coords],C.byref(mask))
                return (coords[0].value,coords[1].value)
            replacement_position=pointer_position();assert replacement_position==(321,234)
            for operation in (lambda:move_pointer(100,100,old_generation),lambda:HeldPointer('1',old_generation).move(100,100)):
                with environment_scope(env):
                    try:operation();raise AssertionError('replacement moved')
                    except DesktopError as exc:assert exc.code=='SESSION_CHANGED'
                assert pointer_position()==replacement_position
            held=oracle.pressed();button_state=oracle.buttons();assert held and button_state
            key_guard.stdin.close();os.kill(key_guard.pid,signal.SIGCONT)
            assert select.select([key_guard.stdout],[],[],4)[0]
            key_proof=json.loads(key_guard.stdout.readline());key_guard.wait(timeout=3)
            assert key_proof['session_changed'] and key_proof['cleanup_skipped'] and not key_proof['cleanup_verified'],key_proof
            mouse_guard.stdin.close();os.kill(mouse_guard.pid,signal.SIGCONT)
            mouse_proof=json.loads(mouse_guard.stdout.readline());mouse_guard.wait(timeout=3)
            assert mouse_proof['session_changed'] and mouse_proof['cleanup_skipped'] and not mouse_proof['cleanup_verified'],mouse_proof
            assert oracle.pressed()==held and oracle.buttons()==button_state and pointer_position()==replacement_position
            explicit=native({'operation':'release','button':'1','server_generation':old_generation})
            assert explicit['session_changed'] and explicit['cleanup_skipped'] and oracle.buttons()==button_state
            # A failed old cleanup can be explicitly resolved by generation
            # proof in its ORIGINAL environment, without releasing new keys.
            fake=subprocess.Popen([sys.executable,'-c','import json;print(json.dumps(dict(armed=True,effect="uncertain",cleanup_verified=False)))'],stdout=subprocess.PIPE)
            hooks=(keyboard._retain_recovery,keyboard._release_recovery);retained=[];released=[]
            try:
                keyboard.set_recovery_hooks(retained.append,released.append)
                with environment_scope(env):keyboard._retain_guardian(fake,b'',plan)
                fake.wait(timeout=3);time.sleep(.03)
                with environment_scope(dict(env,DISPLAY=':invalid-backend')):
                    proof=keyboard.recover_keyboard_input()
                assert proof['resolved_count']==1 and proof['pending_count']==0,proof
                assert proof['recoveries'][0]['proof']=='original_server_replaced'
                assert retained==released and oracle.pressed()==held and oracle.buttons()==button_state
            finally:keyboard.set_recovery_hooks(*hooks)
            command('xdotool','keyup','Control_L');command('xdotool','mouseup','1')
            print(json.dumps({'same_display':env['DISPLAY'],'same_authority_path':True,'generation_changed':True,
                              'keyboard_cleanup':'skipped; replacement matching held key preserved',
                              'mouse_cleanup':'skipped; replacement held button and pointer position preserved',
                              'explicit_recovery':'original environment used; replacement proof resolved quarantine without input'},indent=2))
        finally:
            if mouse_writer is not None:os.close(mouse_writer)
            for guard in (key_guard,mouse_guard):
                if guard:
                    if guard.stdin and not guard.stdin.closed:guard.stdin.close()
                    if guard.poll() is None:os.kill(guard.pid,signal.SIGCONT);guard.wait(timeout=4)
                    if guard.stdout:guard.stdout.close()
            if oracle:oracle.close()
            if stall_cleanup and server and server.poll() is None:
                # Inject only after the oracle connection has closed: closing
                # Xlib against a deliberately stopped server can itself block.
                os.kill(server.pid,signal.SIGSTOP)
                wait(lambda:Path(f'/proc/{server.pid}/status').read_text().split('State:',1)[1].lstrip().startswith('T'))
            try:
                if server:
                    cleanup=stop_owned_server(server)
                    print(json.dumps({'owned_xvfb_cleanup':cleanup}),flush=True)
                    if stall_cleanup:assert cleanup['term_to_kill_escalated'] and cleanup['returncode']==-signal.SIGKILL,cleanup
            finally:
                os.environ.clear();os.environ.update(original_env)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exercise-stalled-xvfb-cleanup',action='store_true',help='Stop only the owned replacement Xvfb after all input assertions; require bounded TERM/KILL cleanup.')
    main(parser.parse_args().exercise_stalled_xvfb_cleanup)
