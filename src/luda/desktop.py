import base64
from contextlib import contextmanager
import fcntl
import hashlib
import io
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid

from PIL import Image
from .common import DesktopError, display_identity, checkpoint, mark_effect, process_identity, run, stop_process, validate_text
from .x11 import X11
from .interaction import InteractionMixin
from .control import Control


class Desktop(InteractionMixin):
    def __init__(self):
        self.x = None
        self.closed = False
        self.snapshots = {}
        self.elements = {}
        self.windows = {}
        self.clipboard_owner = None
        self.local_lock = threading.Lock()
        name = hashlib.sha256(display_identity(os.environ.get('DISPLAY','')).encode()).hexdigest()[:12]
        directory = Path(tempfile.gettempdir()) / f'silo-desktop-{os.getuid()}'
        directory.mkdir(mode=0o700, exist_ok=True)
        if directory.is_symlink() or directory.stat().st_uid != os.getuid() or directory.stat().st_mode & 0o077:
            raise DesktopError('UNSAFE_RUNTIME', 'Runtime directory must be owned by this account and mode 0700.')
        self.lockfd = os.open(directory/f'{name}.lock', os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW, 0o600)
        self.runtime = directory
        self.control = Control(directory, name)

    @contextmanager
    def transaction(self):
        if self.closed:
            raise DesktopError('CLOSED', 'Server backend has been closed.')
        checkpoint()
        if not self.local_lock.acquire(blocking=False):
            raise DesktopError('BUSY', 'Another operation is in progress; no input sent.')
        try:
            try:
                fcntl.flock(self.lockfd, fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise DesktopError('BUSY', 'Another tool server controls this display; no input sent.') from exc
            try:
                yield
            finally:
                fcntl.flock(self.lockfd, fcntl.LOCK_UN)
        finally:
            self.local_lock.release()

    def display(self):
        if self.x is None:
            self.x = X11()
        return self.x

    def doctor(self):
        dependencies = {c: shutil.which(c) is not None for c in ('xdotool','wmctrl','scrot','xclip','xprop')}
        result = {'version':'0.1.0','backend':'X11 + AT-SPI','dependencies':dependencies,
                  'display':os.environ.get('DISPLAY'),'session_bus':bool(os.environ.get('DBUS_SESSION_BUS_ADDRESS')),
                  'uid':os.getuid(),'transport':'stdio','support':'experimental X11; Wayland unsupported',
                  'limitations':['Human viewer input is not locked out.','No automatic clipboard restoration.',
                                 'Accessibility mapping requires matching top-level geometry.','No automatic retry of mutations.']}
        try:
            result['geometry'] = self.display().geometry(self.display().root)
            result['display_available'] = True
        except DesktopError as exc:
            result.update(display_available=False,display_error=str(exc))
        try:
            check = run(['/usr/bin/python3','-c',"import gi;gi.require_version('Atspi','2.0');from gi.repository import Atspi;Atspi.set_timeout(600,1000);print(Atspi.get_desktop(0).get_child_count())"],timeout=4)
            result['accessible_applications'] = int(check)
            result['accessibility_available'] = True
        except DesktopError as exc:
            result['accessibility_available'] = False
            result['accessibility_error'] = str(exc)
        result['ready'] = all(dependencies.values()) and result['display_available'] and result['session_bus'] and result['accessibility_available']
        return result

    def active(self):
        try:
            return int(run(['xdotool','getactivewindow']).strip())
        except DesktopError:
            return None

    def list_windows(self):
        try:
            rows = run(['wmctrl','-lp']).decode(errors='replace').splitlines()
        except DesktopError as exc:
            if exc.code == 'BACKEND_ERROR' and 'Cannot get client list properties' in str(exc):
                self.windows = {}
                return []
            raise
        active = self.active()
        result = []
        for line in rows:
            fields = line.split(None, 4)
            if len(fields) < 4:
                continue
            xid, workspace, pid = int(fields[0],16), int(fields[1]), int(fields[2])
            if pid <= 0:
                continue
            try:
                start = process_identity(pid)
                bounds = self.display().geometry(xid)
            except DesktopError:
                continue
            frame = dict(bounds)
            prop = run(['xprop','-id',str(xid),'_NET_FRAME_EXTENTS','WM_CLASS']).decode()
            frame_prop = prop.splitlines()[0]
            wm_class = re.findall(r'"([^"]*)"', prop.partition('WM_CLASS')[2])
            if '=' in frame_prop:
                values = [int(v) for v in re.findall(r'\d+',frame_prop.split('=',1)[1])]
                if len(values)==4:
                    left,right,top,bottom=values
                    frame={'x':bounds['x']-left,'y':bounds['y']-top,'width':bounds['width']+left+right,'height':bounds['height']+top+bottom}
            token = f'{xid:x}:{pid}:{start}'
            item = {'window_id':token,'xid':xid,'pid':pid,'start':start,
                    'title':fields[4][:512] if len(fields)>4 else '', 'workspace':workspace,
                    'bounds':bounds,'frame_bounds':frame,'active':xid==active,'wm_class':wm_class}
            result.append(item)
        self.windows = {w['window_id']:w for w in result}
        return result

    def target_window(self, window_id, require_focus=True):
        windows = self.list_windows()
        w = next((w for w in windows if w['window_id']==window_id),None)
        if not w:
            raise DesktopError('STALE_TARGET','Window identity is no longer present; list windows again.')
        if require_focus and not w['active']:
            raise DesktopError('FOCUS_CHANGED','Target is not active. Activate it, inspect, then act.')
        return w

    def activate(self, window_id):
        w = self.target_window(window_id,False)
        run(['xdotool','windowactivate',str(w['xid'])],effect='uncertain')
        deadline = time.monotonic()+1.5
        while time.monotonic()<deadline:
            if self.active()==w['xid']:
                return {'effect':'verified','window_id':window_id,'verification':'active window matches'}
            time.sleep(.04)
        raise DesktopError('ACTIVATION_FAILED','Window did not become active.',effect='uncertain')

    def signature(self, windows):
        return [(w['window_id'], w['bounds'], w['active'], w['workspace']) for w in windows]

    def observe(self, max_width=1280):
        if not 320 <= max_width <= 2560:
            raise DesktopError('INVALID_ARGUMENT','max_width must be 320–2560.')
        before = self.list_windows()
        with tempfile.TemporaryDirectory(dir=self.runtime) as directory:
            path = str(Path(directory)/'screen.png')
            run(['scrot','--overwrite',path],timeout=4)
            with Image.open(path) as source:
                native = source.size
                height = max(1, round(source.height * min(1,max_width/source.width)))
                width = min(source.width,max_width)
                source = source.convert('RGB').resize((width,height))
                buf = io.BytesIO();source.save(buf,format='PNG')
        after = self.list_windows()
        if self.signature(before)!=self.signature(after):
            raise DesktopError('DESKTOP_CHANGED','Window layout changed during capture; observe again.')
        token = uuid.uuid4().hex
        now = time.monotonic()
        self.snapshots = {k:v for k,v in self.snapshots.items() if now-v['time']<15}
        snapshot = {'time':now,'signature':self.signature(after),'native':native,'image':(width,height)}
        self.snapshots[token] = snapshot
        while len(self.snapshots)>16:self.snapshots.pop(next(iter(self.snapshots)))
        return {'snapshot_id':token,'expires_after_seconds':15,
                'coordinate_space':'returned image pixels; pass snapshot_id with pointer actions',
                'image_size':{'width':width,'height':height},
                'desktop_size':{'width':native[0],'height':native[1]},
                'windows':after,'image_base64':base64.b64encode(buf.getvalue()).decode()}

    def point(self, window_id, snapshot_id, x, y):
        snap = self.snapshots.get(snapshot_id)
        if not snap or time.monotonic()-snap['time']>=15:
            raise DesktopError('STALE_OBSERVATION','Screenshot expired or belongs to another server; observe again.')
        w = self.target_window(window_id)
        if self.signature(list(self.windows.values())) != snap['signature']:
            raise DesktopError('STALE_OBSERVATION','Window layout or focus changed; observe again.')
        root = self.display().geometry(self.display().root)
        if (root['width'],root['height']) != tuple(snap['native']):
            raise DesktopError('STALE_OBSERVATION','Display resolution changed; observe again.')
        iw, ih = snap['image'];nw, nh = snap['native']
        if not 0 <= x < iw or not 0 <= y < ih:
            raise DesktopError('OUT_OF_BOUNDS','Point is outside the returned screenshot.')
        px, py = int(x*nw/iw),int(y*nh/ih)
        b = w['bounds']
        if not b['x'] <= px < b['x']+b['width'] or not b['y'] <= py < b['y']+b['height']:
            raise DesktopError('OUT_OF_BOUNDS','Point is outside target client bounds; window decorations are excluded.')
        return px,py

    def pointer(self, window_id, snapshot_id, x, y, kind='click', button='left', count=1, end_x=None,end_y=None,direction='down'):
        if kind not in ('click', 'scroll', 'drag'):
            raise DesktopError('INVALID_ARGUMENT', 'Unknown pointer action; no input sent.')
        if direction not in ('up', 'down', 'left', 'right'):
            raise DesktopError('INVALID_ARGUMENT', 'Invalid scroll direction; no input sent.')
        if isinstance(count, bool) or not isinstance(count, int):
            raise DesktopError('INVALID_ARGUMENT', 'Count must be an integer.')
        coordinates = (x, y, end_x, end_y) if kind == 'drag' else (x, y)
        if any(isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) for v in coordinates):
            raise DesktopError('INVALID_ARGUMENT', 'Coordinates must be finite numbers.')
        px,py = self.point(window_id,snapshot_id,x,y)
        end = self.point(window_id,snapshot_id,end_x,end_y) if kind=='drag' else None
        buttons = {'left':'1','middle':'2','right':'3'}
        if button not in buttons or not 1 <= count <= 20:
            raise DesktopError('INVALID_ARGUMENT','Invalid button or count.')
        run(['xdotool','mousemove',str(px),str(py)],effect='uncertain')
        if kind=='click':
            run(['xdotool','click','--repeat',str(count),'--delay','100',buttons[button]],effect='uncertain')
        elif kind=='scroll':
            mapping={'up':'4','down':'5','left':'6','right':'7'}
            if direction not in mapping:
                raise DesktopError('INVALID_ARGUMENT','Invalid scroll direction.')
            run(['xdotool','click','--repeat',str(count),'--delay','35',mapping[direction]],effect='uncertain')
        elif kind=='drag':
            try:
                run(['xdotool','mousedown',buttons[button]],effect='uncertain')
                for step in range(1,11):
                    ax=round(px+(end[0]-px)*step/10);ay=round(py+(end[1]-py)*step/10)
                    run(['xdotool','mousemove',str(ax),str(ay)],effect='uncertain');time.sleep(.02)
            finally:
                run(['xdotool','mouseup',buttons[button]],effect='uncertain',cleanup=True,timeout=1)
        return {'effect':'dispatched','verification':'Observe the resulting application state.'}

    def key(self, window_id, chord):
        self.target_window(window_id)
        parts=chord.split('+')
        modifiers={'ctrl','alt','shift','super'}
        named={'Return','Tab','Escape','BackSpace','Delete','Home','End','Left','Right','Up','Down','Page_Up','Page_Down','Insert','space'}
        if not parts or any(p not in modifiers for p in parts[:-1]) or not (parts[-1] in named or re.fullmatch(r'[A-Za-z0-9]|F(?:[1-9]|1[0-9]|2[0-4])',parts[-1])):
            raise DesktopError('INVALID_KEY','Use e.g. ctrl+s, ctrl+shift+v, Return, Tab, or Escape. Text belongs in enter_text.')
        run(['xdotool','key','--clearmodifiers',chord],effect='uncertain')
        return {'effect':'dispatched','verification':'Key delivery does not prove application outcome.'}

    def ax(self, request, mutating=False):
        worker = str(Path(__file__).with_name('ax_worker.py'))
        try:
            raw = run(['/usr/bin/python3',worker],data=json.dumps(request).encode(),timeout=5)
        except DesktopError as exc:
            if mutating and exc.code != 'DEPENDENCY_MISSING':
                exc.effect = 'uncertain'
                mark_effect()
            raise
        result = json.loads(raw)
        if 'error' in result:
            effect = result.get('effect', 'uncertain' if mutating and result['error']=='ACCESSIBILITY_ERROR' else 'none')
            mark_effect(effect)
            raise DesktopError(result['error'],result.get('message','Accessibility failed.'),effect=effect)
        if mutating:
            mark_effect(result.get('effect', 'dispatched'))
        return result

    def inspect(self, window_id, limit=150, name=None, role=None, states=None, max_depth=30):
        if not 1 <= limit <= 500:
            raise DesktopError('INVALID_ARGUMENT','limit must be 1–500.')
        w = self.target_window(window_id,False)
        result = self.ax({'op':'inspect','pid':w['pid'],'start':w['start'],'limit':limit,'bounds':w['bounds'],'frame_bounds':w['frame_bounds'],'window_title':w['title'],'filters':{k:v for k,v in {'name':name,'role':role,'states':states}.items() if v is not None},'max_depth':max_depth})
        now=time.monotonic()
        self.elements={k:v for k,v in self.elements.items() if now-v['time']<60}
        tokens = {node['path']:uuid.uuid4().hex for node in result['nodes']}
        for node in result['nodes']:
            token=tokens[node['path']]
            self.elements[token]={'time':now,'window_id':window_id,'node':dict(node)}
            node['element_id']=token
            node['parent_element_id']=tokens.get(node.pop('parent_path',None))
            node.pop('path',None);node.pop('start',None);node.pop('root_path',None)
        while len(self.elements)>4000:self.elements.pop(next(iter(self.elements)))
        result['window_id']=window_id
        result['element_expiry_seconds']=60
        return result

    def element(self, element_id, op, **kwargs):
        target=self.elements.get(element_id)
        if not target or time.monotonic()-target['time']>=60:
            raise DesktopError('STALE_TARGET','Element expired or belongs to another server; inspect again.')
        w=self.target_window(target['window_id'],op!='read')
        node=target['node']
        if node['start']!=w['start']:
            raise DesktopError('STALE_TARGET','Process identity changed.')
        if op in ('set','insert'):
            validate_text(kwargs['text'])
        return self.ax({'op':op,'pid':w['pid'],'start':w['start'],'target':node,**kwargs},op!='read')

    def paste(self, window_id, text, shortcut=None):
        validate_text(text)
        target = self.target_window(window_id)
        if shortcut is None:
            terminal_classes = {'xfce4-terminal','gnome-terminal','org.gnome.terminal','konsole','kitty','alacritty'}
            classes = {v.casefold() for v in target.get('wm_class', [])}
            if 'xterm' in classes:
                raise DesktopError('UNSUPPORTED_PASTE', 'xterm clipboard bindings vary. Use an explicit shortcut only after inspecting its configured selection behavior.')
            shortcut = 'ctrl_shift_v' if classes & terminal_classes else 'ctrl_v'
        chords={'ctrl_v':'ctrl+v','ctrl_shift_v':'ctrl+shift+v','shift_insert':'shift+Insert'}
        if shortcut not in chords:
            raise DesktopError('INVALID_ARGUMENT','Choose the application clipboard shortcut explicitly.')
        if not text:
            return {'effect':'none','reason':'Empty paste is a no-op; use set_text to clear an editable element.'}
        payload=text.encode('utf-8')
        if self.clipboard_owner:
            mark_effect();stop_process(self.clipboard_owner)
        with tempfile.NamedTemporaryFile(dir=self.runtime) as source:
            source.write(payload);source.flush()
            mark_effect()
            self.clipboard_owner=subprocess.Popen(['xclip','-quiet','-selection','clipboard','-in',source.name],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            deadline=time.monotonic()+1
            while True:
                try:
                    observed=run(['xclip','-selection','clipboard','-out'],timeout=.3)
                    if observed==payload:break
                except DesktopError as exc:
                    if exc.code in ('CANCELLED', 'TIMEOUT'):
                        checkpoint()
                checkpoint()
                if time.monotonic()>deadline:
                    raise DesktopError('CLIPBOARD_FAILED','Could not verify clipboard ownership; no paste key sent.',effect='uncertain')
                time.sleep(.03)
        # Recheck focus after preparing clipboard. Never activate implicitly during paste.
        try:
            self.target_window(window_id)
            if self.clipboard_owner.poll() is not None or run(['xclip','-selection','clipboard','-out'],timeout=.5) != payload:
                raise DesktopError('CLIPBOARD_CHANGED', 'Clipboard ownership or contents changed before paste; no shortcut sent.', effect='uncertain')
            self.key(window_id,chords[shortcut])
        except DesktopError as exc:
            exc.details['clipboard_changed'] = True
            exc.effect = 'uncertain'
            raise
        return {'effect':'dispatched','shortcut':shortcut,'clipboard_exact_match':True,
                'clipboard_verification':'Sampled immediately before shortcut; other clients can still intervene.',
                'verification':'Destination text is not verified. Inspect for paste dialogs or read the target element.',
                'clipboard':'CLIPBOARD replaced until another owner takes it or this server exits. PRIMARY is unchanged.',
                'warning':'Shift+Insert can select PRIMARY in some terminals. A terminal may execute pasted newlines; no confirmation dialog is automatically accepted.'}

    def wait_for(self, condition, window_id=None, element_id=None, text=None, timeout=5):
        if isinstance(timeout, bool) or not isinstance(timeout, (int,float)) or not 0 <= timeout <= 10:
            raise DesktopError('INVALID_ARGUMENT', 'timeout must be 0–10 seconds.')
        conditions = {'window_present', 'window_absent', 'window_active', 'text_equals', 'text_contains'}
        if condition not in conditions:
            raise DesktopError('INVALID_ARGUMENT', 'Unknown wait condition.')
        if condition.startswith('window_'):
            if not window_id or element_id is not None or text is not None:
                raise DesktopError('INVALID_ARGUMENT', 'Window conditions require only window_id.')
        elif not element_id or not isinstance(text,str) or window_id is not None:
            raise DesktopError('INVALID_ARGUMENT', 'Text conditions require only element_id and text.')
        deadline = time.monotonic()+timeout
        polls = 0
        while True:
            checkpoint()
            polls += 1
            if condition.startswith('window_'):
                current = next((w for w in self.list_windows() if w['window_id']==window_id),None)
                matched = (current is not None if condition=='window_present' else
                           current is None if condition=='window_absent' else
                           bool(current and current['active']))
            else:
                observed = self.element(element_id,'read',limit=1_000_000)
                if observed['truncated']:
                    raise DesktopError('VERIFICATION_LIMIT', 'Target text exceeds the full-read verification budget.')
                matched = observed['text']==text if condition=='text_equals' else text in observed['text']
            if matched:
                return {'effect':'verified','condition':condition,'matched':True,'polls':polls}
            remaining = deadline-time.monotonic()
            if remaining <= 0:
                return {'effect':'none','condition':condition,'matched':False,'polls':polls,'reason':'condition_timeout'}
            time.sleep(min(.1,remaining))

    def close(self):
        if self.closed:
            return
        self.closed = True
        errors = []
        for cleanup in (lambda: stop_process(self.clipboard_owner) if self.clipboard_owner else None,
                        lambda: self.x.close() if self.x else None,
                        lambda: os.close(self.lockfd)):
            try:
                cleanup()
            except Exception as exc:
                errors.append(str(exc))
        self.cleanup_errors = errors
