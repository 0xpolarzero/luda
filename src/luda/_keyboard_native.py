"""Private isolated XKB/XTest helper. Never imported by the MCP server."""
from contextlib import contextmanager
import ctypes as C
import json
import sys
import time
from ._x11_helper import _NativeX11, _decode_window_token
from .common import DesktopError
from ._input_native import generation
from .input_validation import validate_generation


class State(C.Structure):
    _fields_=[('group',C.c_ubyte),('locked_group',C.c_ubyte),('base_group',C.c_ushort),('latched_group',C.c_ushort)]+[(name,C.c_ubyte) for name in ('mods','base_mods','latched_mods','locked_mods','compat_state','grab_mods','compat_grab_mods','lookup_mods','compat_lookup_mods')]+[('ptr_buttons',C.c_ushort)]
class ModifierMap(C.Structure):
    _fields_=[('max_keypermod',C.c_int),('modifiermap',C.POINTER(C.c_ubyte))]
class Buttons(C.Structure):
    _fields_=[('mask_len',C.c_int),('mask',C.POINTER(C.c_ubyte))]
class Modifiers(C.Structure):
    _fields_=[(name,C.c_int) for name in ('base','latched','locked','effective')]


class Keyboard:
    def __init__(self):
        self.x=_NativeX11();x=self.x.lib
        from ._private_input import bind_private_input
        self.private=bind_private_input(self.x)
        self._grab_depth=0
        x.XQueryKeymap.argtypes=[C.c_void_p,C.c_void_p]
        x.XkbGetState.argtypes=[C.c_void_p,C.c_uint,C.POINTER(State)]
        x.XStringToKeysym.argtypes=[C.c_char_p];x.XStringToKeysym.restype=C.c_ulong
        x.XKeysymToKeycode.argtypes=[C.c_void_p,C.c_ulong];x.XKeysymToKeycode.restype=C.c_ubyte
        x.XkbLookupKeySym.argtypes=[C.c_void_p,C.c_ubyte,C.c_uint,C.POINTER(C.c_uint),C.POINTER(C.c_ulong)]
        x.XGetModifierMapping.argtypes=[C.c_void_p];x.XGetModifierMapping.restype=C.POINTER(ModifierMap)
        x.XFreeModifiermap.argtypes=[C.POINTER(ModifierMap)]
        x.XSync.argtypes=[C.c_void_p,C.c_int];x.XFree.argtypes=[C.c_void_p]
        x.XCreateSimpleWindow.argtypes=[C.c_void_p,C.c_ulong,C.c_int,C.c_int,C.c_uint,C.c_uint,C.c_uint,C.c_ulong,C.c_ulong];x.XCreateSimpleWindow.restype=C.c_ulong
        x.XKillClient.argtypes=[C.c_void_p,C.c_ulong]
        self.test=C.CDLL('libXtst.so.6')
        self.test.XTestFakeKeyEvent.argtypes=[C.c_void_p,C.c_uint,C.c_int,C.c_ulong]
        self.test.XTestQueryExtension.argtypes=[C.c_void_p]+[C.POINTER(C.c_int)]*4
        extension=[C.c_int() for _ in range(4)]
        if not self.test.XTestQueryExtension(self.x.display,*[C.byref(value) for value in extension]):
            raise DesktopError('KEYBOARD_UNAVAILABLE','XTest extension is unavailable.')
        self.xi=C.CDLL('libXi.so.6')
        self.xi.XIQueryVersion.argtypes=[C.c_void_p,C.POINTER(C.c_int),C.POINTER(C.c_int)]
        major,minor=C.c_int(2),C.c_int(0)
        if self.xi.XIQueryVersion(self.x.display,C.byref(major),C.byref(minor))!=0:
            raise DesktopError('KEYBOARD_UNAVAILABLE','XInput 2 extension is unavailable.')
        self.xi.XIGetClientPointer.argtypes=[C.c_void_p,C.c_ulong,C.POINTER(C.c_int)]
        self.xi.XIQueryPointer.argtypes=[C.c_void_p,C.c_int,C.c_ulong,C.POINTER(C.c_ulong),C.POINTER(C.c_ulong)]+[C.POINTER(C.c_double)]*4+[C.POINTER(Buttons),C.POINTER(Modifiers),C.POINTER(Modifiers)]
    def state(self):
        state=State()
        if self.x.lib.XkbGetState(self.x.display,0x100,C.byref(state)):
            raise DesktopError('KEYBOARD_UNAVAILABLE','Cannot query XKB state.')
        return state
    def pressed(self):
        data=(C.c_ubyte*32)();self.x.lib.XQueryKeymap(self.x.display,data)
        return [code for code in range(8,256) if data[code//8] & (1<<(code%8))]
    def buttons(self):
        device=C.c_int();root,child=C.c_ulong(),C.c_ulong();coords=[C.c_double() for _ in range(4)]
        buttons=Buttons();mods,group=Modifiers(),Modifiers()
        if not self.xi.XIGetClientPointer(self.x.display,0,C.byref(device)):
            raise DesktopError('KEYBOARD_UNAVAILABLE','Cannot identify the master pointer.')
        try:
            if not self.xi.XIQueryPointer(self.x.display,device,self.x.root,C.byref(root),C.byref(child),*[C.byref(v) for v in coords],C.byref(buttons),C.byref(mods),C.byref(group)):
                raise DesktopError('KEYBOARD_UNAVAILABLE','Cannot inspect held pointer buttons.')
            if not 0<=buttons.mask_len<=256:
                raise DesktopError('KEYBOARD_UNAVAILABLE','Pointer button map exceeds the supported bound.')
            return [bit for bit in range(buttons.mask_len*8) if buttons.mask[bit//8] & (1<<(bit%8))]
        finally:
            if buttons.mask:self.x.lib.XFree(buttons.mask)
    def symbol(self,name):return self.x.lib.XStringToKeysym(name.encode('ascii'))
    def modifier(self,name):
        symbol=self.symbol(name);code=self.x.lib.XKeysymToKeycode(self.x.display,symbol)
        mapping=self.x.lib.XGetModifierMapping(self.x.display)
        if not mapping:raise DesktopError('KEYBOARD_UNAVAILABLE','Cannot query modifier mapping.')
        try:
            width=mapping.contents.max_keypermod
            if not 0<width<=32:raise DesktopError('UNSUPPORTED_KEYMAP','Unsupported modifier mapping.')
            masks=[1<<i for i in range(8) if code and code in mapping.contents.modifiermap[i*width:(i+1)*width]]
            if len(masks)!=1:raise DesktopError('UNSUPPORTED_KEYMAP','Requested modifier is not mapped uniquely.')
            return code,masks[0]
        finally:self.x.lib.XFreeModifiermap(mapping)
    def lookup(self,code,mask,group):
        consumed=C.c_uint();symbol=C.c_ulong()
        okay=self.x.lib.XkbLookupKeySym(self.x.display,code,mask | ((group&3)<<13),C.byref(consumed),C.byref(symbol))
        return symbol.value if okay else None
    def target_token(self,target,expected=None):
        if type(target) is not int or not 0<target<=0xffffffff:
            raise DesktopError('INVALID_ARGUMENT','Invalid native target window.')
        if expected is not None:validate_generation(expected)
        if expected is None:
            # Direct low-level callers may capture current identity. Production
            # Desktop.key always supplies the token already observed by Desktop.
            return self.x.window_tokens([target])[target]
        prop=self.x._property(target,'_LUDA_WINDOW_TOKEN',9)
        if not prop or _decode_window_token(*prop)!=expected:
            raise DesktopError('STALE_TARGET','Target window generation changed; no keys pressed.')
        return expected

    def plan(self,chord,target,target_generation=None,count=1):
        from .keyboard import validate_chord,validate_key_count
        parts=validate_chord(chord)
        validate_key_count(count)
        target_token=self.target_token(target,target_generation)
        state=self.state()
        if self.pressed() or self.buttons() or state.base_mods:
            raise DesktopError('INPUT_HELD','Keys or pointer buttons are already held; release them before requesting a chord. No input changed.')
        if state.latched_mods or state.latched_group:
            raise DesktopError('UNSUPPORTED_INPUT_STATE','Latched keyboard state is active; no input changed.')
        self.require_focus(target)
        names={'ctrl':'Control_L','shift':'Shift_L','alt':'Alt_L','super':'Super_L'}
        codes=[self.modifier(names[name])[0] for name in parts[:-1]]
        shift,mask=self.modifier('Shift_L')
        wanted=self.symbol(parts[-1])
        # Shortcut modifiers are deliberate physical chord components: Caps
        # Lock must not silently add Shift to Ctrl+letter. Bare symbol keys use
        # actual locks to resolve their case without toggling Caps Lock.
        locks=state.locked_mods & ~2 if parts[:-1] else state.locked_mods
        found=None
        for implicit in (0,mask):
            for code in range(8,256):
                if self.lookup(code,locks | implicit,state.group)==wanted:
                    found=(code,implicit);break
            if found:break
        if found is None:
            raise DesktopError('UNSUPPORTED_KEYMAP','Named key is unavailable in the current keyboard group without changing the layout.')
        code,implicit=found
        if implicit and shift not in codes:codes.append(shift)
        codes.append(code)
        if len(codes)!=len(set(codes)) or not 1<=len(codes)<=5:
            raise DesktopError('UNSUPPORTED_KEYMAP','Chord has overlapping keycodes.')
        return {'chord':chord,'target':target,'keycodes':codes,'group':state.group,'locked_mods':state.locked_mods,'server_generation':generation(self.x),'target_generation':target_token,'count':count}
    def press_target(self,code,target,target_generation):
        # The server cannot destroy/reuse a target between this identity check
        # and its key-down. Never keep the grab across sleeps or application
        # work; disconnecting this isolated helper also releases the grab.
        with self.guard():
            self.target_token(target,target_generation)
            self.require_focus(target)
            self.event(code,True)

    def client_resource(self):
        resource=self.x.lib.XCreateSimpleWindow(self.x.display,self.x.root,0,0,1,1,0,0,0)
        token=self.x.window_tokens([resource])[resource]
        return {'xid':resource,'generation':token}
    def disconnect_injector(self,client):
        # The owned nonce prevents killing an unrelated client after resource
        # ID reuse. This request and all key releases share one X connection,
        # so any still-buffered injector requests are discarded first.
        if not isinstance(client,dict) or type(client.get('xid')) is not int or not 0<client['xid']<=0xffffffff:
            raise ValueError()
        # Serialize the nonce check and disconnect against other clients. One
        # X connection orders our requests but alone cannot prevent an XID
        # being reassigned between the property reply and XKillClient.
        x=self.x.lib
        x.XGrabServer.argtypes=[C.c_void_p]
        x.XUngrabServer.argtypes=[C.c_void_p]
        x.XGrabServer(self.x.display)
        try:
            try:
                prop=self.x._property(client['xid'],'_LUDA_WINDOW_TOKEN',9)
                if prop and _decode_window_token(*prop)==client.get('generation'):
                    x.XKillClient(self.x.display,client['xid'])
                    x.XSync(self.x.display,False)
            except DesktopError as exc:
                if exc.code!='STALE_TARGET':raise
        finally:
            # Cancellation kills this isolated process and closes its X
            # connection, which also releases the grab if normal cleanup fails.
            x.XUngrabServer(self.x.display)
            x.XSync(self.x.display,False)

    def require_focus(self,target):
        self.private.validate()
        window=self.private.focus_window()
        # Toolkits may focus a child input window. Keep that focus rather than
        # forcing the top-level between each key of an IME or popup interaction.
        x=self.x.lib
        x.XQueryTree.argtypes=[C.c_void_p,C.c_ulong,C.POINTER(C.c_ulong),C.POINTER(C.c_ulong),C.POINTER(C.POINTER(C.c_ulong)),C.POINTER(C.c_uint)]
        for _ in range(64):
            if window==target:return
            if window in (0,1,self.x.root):break
            root,parent=C.c_ulong(),C.c_ulong();children=C.POINTER(C.c_ulong)();count=C.c_uint()
            okay=x.XQueryTree(self.x.display,window,C.byref(root),C.byref(parent),C.byref(children),C.byref(count))
            if children:x.XFree(children)
            if not okay or parent.value==window:break
            window=parent.value
        raise DesktopError('FOCUS_CHANGED','The agent keyboard no longer targets this window; no input sent.')

    @contextmanager
    def guard(self):
        # Device removal may reset a connection's ClientPointer to the human
        # pair. Serialize identity validation and dispatch against that race.
        first=self._grab_depth==0
        if first:self.x.lib.XGrabServer(self.x.display)
        self._grab_depth+=1
        try:
            self.private.validate()
            yield
        finally:
            self._grab_depth-=1
            if first:
                self.x.lib.XUngrabServer(self.x.display)
                self.x.lib.XSync(self.x.display,False)

    def focus_target(self,target,token):
        with self.guard():
            self.target_token(target,token)
            try:self.require_focus(target)
            except DesktopError as exc:
                if exc.code!='FOCUS_CHANGED':raise
                self.private.focus(target)
            self.require_focus(target)

    def event(self,code,down):
        with self.guard():
            if not self.test.XTestFakeKeyEvent(self.x.display,code,down,0):
                raise DesktopError('KEYBOARD_UNAVAILABLE','XTest key dispatch failed.',effect='uncertain')
            self.x.lib.XSync(self.x.display,False)
    def close(self):self.x.close()


def emit(value):print(json.dumps(value),flush=True)


def main():
    keyboard=None
    try:
        request=json.loads(sys.stdin.buffer.readline(4097))
        keyboard=Keyboard()
        if sys.argv[1]=='probe':
            state=keyboard.state()
            emit({'available':True,'backend':'private XI2 + XKB + XTest','group':state.group,'locked_mods':state.locked_mods,
                  'input_held':bool(keyboard.pressed() or keyboard.buttons() or state.base_mods),
                  'latched_input':bool(state.latched_mods or state.latched_group),
                  'mapping':'Current group, named keys with ordinary Shift; unsupported symbols are refused.',
                  'cleanup':'Owned injector termination and release on the private agent devices only.'})
        elif sys.argv[1]=='check_focus':
            keyboard.target_token(request['target'],request['target_generation'])
            keyboard.require_focus(request['target'])
            emit({'effect':'none','agent_focus':True})
        elif sys.argv[1]=='focus':
            keyboard.focus_target(request['target'],request['target_generation'])
            emit({'effect':'verified','agent_focus':True})
        elif sys.argv[1]=='plan':emit(keyboard.plan(request['chord'],request['target'],request.get('target_generation'),request.get('count',1)))
        elif sys.argv[1]=='release':
            codes=request['keycodes']
            if not isinstance(codes,list) or not 1<=len(codes)<=5 or any(type(c) is not int or not 8<=c<=255 for c in codes):raise ValueError()
            if generation(keyboard.x)!=request['server_generation']:
                emit({'released':False,'session_changed':True,'cleanup_skipped':True});return
            keyboard.disconnect_injector(request['client'])
            for code in reversed(codes):keyboard.event(code,False)
            emit({'released':not set(codes).intersection(keyboard.pressed())})
        elif sys.argv[1]=='inject':
            if generation(keyboard.x)!=request['server_generation']:
                raise DesktopError('SESSION_CHANGED','X server changed before injection; no keys pressed.')
            if keyboard.plan(request['chord'],request['target'],request.get('target_generation'),request.get('count',1))!=request:
                raise DesktopError('KEYMAP_CHANGED','Keyboard state changed before dispatch; no input sent.')
            emit({'armed':True,'client':keyboard.client_resource(),'dispatch_progress_version':1})
            for repetition in range(request['count']):
                if repetition and keyboard.plan(request['chord'],request['target'],request['target_generation'],request['count'])!=request:
                    raise DesktopError('KEYMAP_CHANGED','Keyboard state changed between repetitions; remaining chords were not sent.',effect='uncertain')
                emit({'dispatch_started':repetition+1})
                pressed=[]
                try:
                    for code in request['keycodes']:
                        pressed.append(code);keyboard.press_target(code,request['target'],request['target_generation']);time.sleep(.012)
                finally:
                    for code in reversed(pressed):keyboard.event(code,False)
                state=keyboard.state()
                if state.group!=request['group'] or state.locked_mods!=request['locked_mods']:
                    raise DesktopError('KEYMAP_CHANGED','Keyboard group or locks changed; remaining chords were not sent.',effect='uncertain')
                emit({'dispatch_completed':repetition+1})
                if repetition+1<request['count']:time.sleep(.035)
            emit({'done':True,'effect':'dispatched','group_unchanged':True,'locks_unchanged':True,'dispatched_count':request['count']})
        else:raise ValueError()
    except DesktopError as exc:emit({'code':exc.code,'message':str(exc),'effect':exc.effect})
    except Exception:emit({'code':'KEYBOARD_UNAVAILABLE','message':'Native keyboard helper failed.','effect':'none'})
    finally:
        if keyboard:keyboard.close()


if __name__=='__main__':main()
