"""Same-process, same-XID recreation refuses keys with independent event oracle."""
import ctypes as C
import json,os,select,subprocess,sys
from unittest.mock import patch
from luda.x11 import X11

class Cookie(C.Structure):_fields_=[('sequence',C.c_uint)]

reader,writer=os.pipe()
server=subprocess.Popen(['Xvfb','-displayfd',str(writer),'-screen','0','640x480x24','-nolisten','tcp'],pass_fds=(writer,),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
os.close(writer);connection=None
try:
    assert select.select([reader],[],[],5)[0]
    display=':'+os.read(reader,32).decode().strip();os.close(reader)
    with patch.dict(os.environ,DISPLAY=display):
        driver=X11();root=driver.root
        x=C.CDLL('libxcb.so.1');libc=C.CDLL(None);libc.free.argtypes=[C.c_void_p]
        x.xcb_connect.argtypes=[C.c_char_p,C.c_void_p];x.xcb_connect.restype=C.c_void_p
        x.xcb_disconnect.argtypes=[C.c_void_p]
        x.xcb_generate_id.argtypes=[C.c_void_p];x.xcb_generate_id.restype=C.c_uint32
        x.xcb_create_window_checked.argtypes=[C.c_void_p,C.c_uint8,C.c_uint32,C.c_uint32,C.c_int16,C.c_int16,C.c_uint16,C.c_uint16,C.c_uint16,C.c_uint16,C.c_uint32,C.c_uint32,C.c_void_p];x.xcb_create_window_checked.restype=Cookie
        x.xcb_request_check.argtypes=[C.c_void_p,Cookie];x.xcb_request_check.restype=C.c_void_p
        for name in ('destroy','map'):
            fn=getattr(x,'xcb_'+name+'_window_checked');fn.argtypes=[C.c_void_p,C.c_uint32];fn.restype=Cookie
        x.xcb_set_input_focus_checked.argtypes=[C.c_void_p,C.c_uint8,C.c_uint32,C.c_uint32];x.xcb_set_input_focus_checked.restype=Cookie
        x.xcb_poll_for_event.argtypes=[C.c_void_p];x.xcb_poll_for_event.restype=C.c_void_p
        connection=x.xcb_connect(None,None);xid=x.xcb_generate_id(connection)
        def checked(cookie):assert not x.xcb_request_check(connection,cookie),'XCB request failed'
        def create():
            eventmask=C.c_uint32(3|4|8|64) # key, button and pointer-motion events
            checked(x.xcb_create_window_checked(connection,0,xid,root,10,10,100,80,0,1,0,2048,C.byref(eventmask)))
            checked(x.xcb_map_window_checked(connection,xid))
            checked(x.xcb_set_input_focus_checked(connection,1,xid,0))
            subprocess.run(['xprop','-root','-f','_NET_ACTIVE_WINDOW','32x','-set','_NET_ACTIVE_WINDOW',hex(xid)],check=True,stdout=subprocess.DEVNULL)
        def events(allowed=(2,3)):
            values=[]
            while event:=x.xcb_poll_for_event(connection):
                kind=C.cast(event,C.POINTER(C.c_ubyte))[0]&127
                if kind in allowed:values.append(kind)
                libc.free(event)
            return values
        def helper(operation,request):return json.loads(subprocess.check_output([sys.executable,'-m','luda._keyboard_native',operation],input=json.dumps(request).encode()+b'\n',timeout=3))
        create();old=driver.window_tokens([xid])[xid]
        plan=helper('plan',{'chord':'Return','target':xid,'target_generation':old});assert plan['target_generation']==old
        # Injector emits an ownership record followed by its completion record.
        output=subprocess.check_output([sys.executable,'-m','luda._keyboard_native','inject'],input=json.dumps(plan).encode()+b'\n',timeout=3)
        assert json.loads(output.splitlines()[-1])['done'] and events()==[2,3]
        pointer_request={'button':'1','count':1,'target':xid,'target_generation':old,'position':[30,30]}
        pointer_plan=json.loads(subprocess.check_output([sys.executable,'-m','luda._pointer_native','plan'],input=json.dumps(pointer_request).encode()+b'\n',timeout=3))
        checked(x.xcb_destroy_window_checked(connection,xid));create()
        new=driver.window_tokens([xid])[xid];assert new!=old
        assert events()==[]
        refused=helper('plan',{'chord':'Return','target':xid,'target_generation':old})
        assert refused['code']=='STALE_TARGET' and refused['effect']=='none',refused
        refused=helper('inject',plan)
        assert refused['code']=='STALE_TARGET' and refused['effect']=='none',refused
        assert events()==[],'replacement received key events'
        fresh=helper('plan',{'chord':'Return','target':xid,'target_generation':new})
        output=subprocess.check_output([sys.executable,'-m','luda._keyboard_native','inject'],input=json.dumps(fresh).encode()+b'\n',timeout=3)
        assert json.loads(output.splitlines()[-1])['done'] and events()==[2,3]
        subprocess.run(['xdotool','mousemove','200','200'],check=True)
        events((2,3,4,5,6))
        for operation,request in [('plan',pointer_request),('inject',pointer_plan),('move',{'position':[30,30],'target':xid,'target_generation':old,'server_generation':pointer_plan['server_generation']})]:
            refused=json.loads(subprocess.check_output([sys.executable,'-m','luda._pointer_native',operation],input=json.dumps(request).encode()+b'\n',timeout=3))
            assert refused['code']=='STALE_TARGET' and refused['effect']=='none',refused
            assert events((2,3,4,5,6))==[],'replacement received stale pointer events'
            assert 'X=200\nY=200' in subprocess.check_output(['xdotool','getmouselocation','--shell']).decode()
        pointer_request['target_generation']=new
        pointer_plan=json.loads(subprocess.check_output([sys.executable,'-m','luda._pointer_native','plan'],input=json.dumps(pointer_request).encode()+b'\n',timeout=3))
        output=subprocess.check_output([sys.executable,'-m','luda._pointer_native','inject'],input=json.dumps(pointer_plan).encode()+b'\n',timeout=3)
        assert json.loads(output.splitlines()[-1])['done'] and events((4,5))==[4,5]
        assert 'X=30\nY=30' in subprocess.check_output(['xdotool','getmouselocation','--shell']).decode()
        print(json.dumps({'same_process_same_xid':True,'observed_generation_planner_refused':True,'old_plan_injector_refused':True,'replacement_received_stale_keys':False,'fresh_generation_delivery_verified':True,'stale_pointer_plan_inject_move_refused':True,'replacement_pointer_events':0,'fresh_positioned_click_verified':True}))
finally:
    if connection:x.xcb_disconnect(connection)
    server.terminate();server.wait(timeout=3)
