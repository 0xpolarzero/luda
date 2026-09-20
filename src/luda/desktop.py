import base64
from contextlib import contextmanager
import hashlib
from importlib.metadata import version
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

from PIL import Image, UnidentifiedImageError
from .common import DesktopError, display_identity, checkpoint, mark_effect, process_identity, run, stop_process, validate_text
from .x11 import X11
from .interaction import InteractionMixin
from .control import Control
from .admission import Admission
from .timing import elapsed_time, suspend_offset
from .waits import ConditionWaitsMixin
from types import MappingProxyType
from .common import environment_scope, subprocess_environment
from .input_guard import held_button
from .pointer_input import click_button
from .keyboard import validate_chord, validate_key_count, send_chord, keyboard_capabilities, keyboard_recovery_checkpoint
from .session_state import session_state
from .coordinates import image_bounds, topology_summary
from .ime import composition_capability
from .diagnostics import capability_summary
from .storage import storage_errors, staged_payload


class Desktop(InteractionMixin, ConditionWaitsMixin):
    def __init__(self, environment=None):
        self.environment = MappingProxyType(dict(os.environ if environment is None else environment))
        self.identity_epoch = uuid.uuid4().hex
        self.x = None
        self.closed = False
        self._suspend_offset = suspend_offset()
        self.snapshots = {}
        self.elements = {}
        self.windows = {}
        self.clipboard_owner = None
        self.local_lock = threading.Lock()
        name = hashlib.sha256(display_identity(self.environment.get('DISPLAY','')).encode()).hexdigest()[:12]
        self.lockfd = None
        try:
            with storage_errors('initialize desktop runtime'):
                directory = Path(tempfile.gettempdir()) / f'silo-desktop-{os.getuid()}'
                directory.mkdir(mode=0o700, exist_ok=True)
                if directory.is_symlink() or directory.stat().st_uid != os.getuid() or directory.stat().st_mode & 0o077:
                    raise DesktopError('UNSAFE_RUNTIME', 'Runtime directory must be owned by this account and mode 0700.')
                self.lockfd = os.open(directory/f'{name}.lock', os.O_CREAT|os.O_RDWR|os.O_NOFOLLOW, 0o600)
                self.runtime = directory
                self.control = Control(directory, name)
                self.admission = Admission(directory, name)
        except BaseException:
            if self.lockfd is not None:
                os.close(self.lockfd)
                self.lockfd = None
            raise

    @contextmanager
    def transaction(self):
        if self.closed:
            raise DesktopError('CLOSED', 'Server backend has been closed.')
        try:
            keyboard_recovery_checkpoint()
            checkpoint()
        except DesktopError:
            self.admission.cancel()
            raise
        if not self.local_lock.acquire(blocking=False):
            raise DesktopError('BUSY', 'Another operation is in progress; no input sent.')
        try:
            self.admission.acquire(self.lockfd)
            try:
                offset = suspend_offset()
                if abs(offset-self._suspend_offset) > .05:
                    self.snapshots.clear()
                    self.elements.clear()
                self._suspend_offset = offset
                with environment_scope(self.environment):
                    yield
            finally:
                self.admission.release(self.lockfd)
        finally:
            self.local_lock.release()

    def display(self):
        if self.x is None:
            self.x = X11()
        return self.x

    def doctor(self):
        dependencies = {c: shutil.which(c, path=self.environment.get('PATH', os.defpath)) is not None for c in ('xdotool','wmctrl','scrot','xclip','xprop')}
        result = {'version':version('luda'),'backend':'X11 + AT-SPI','dependencies':dependencies,
                  'display':self.environment.get('DISPLAY'),'session_bus':bool(self.environment.get('DBUS_SESSION_BUS_ADDRESS')),
                  'uid':os.getuid(),'transport':'stdio','support':'experimental X11; Wayland unsupported',
                  'ime_composition':composition_capability(),
                  'limitations':['Human viewer input is not locked out.','No automatic clipboard restoration.',
                                 'Accessibility mapping requires a uniquely identified application window.','No automatic retry of mutations.']}
        try:
            result['geometry'] = self.display().geometry(self.display().root)
            result['display_available'] = True
        except DesktopError as exc:
            result.update(display_available=False,display_error=str(exc))
        try:
            result['display_topology'] = topology_summary(self.display().topology())
            result['topology_available'] = True
        except DesktopError as exc:
            result.update(topology_available=False, topology_error={'code':exc.code,'message':str(exc)})
        try:
            check = run(['/usr/bin/python3','-c',"import gi;gi.require_version('Atspi','2.0');from gi.repository import Atspi;Atspi.set_timeout(600,1000);print(Atspi.get_desktop(0).get_child_count())"],timeout=4)
            count = int(check)
            if count < 0:raise ValueError()
            result['accessible_applications'] = count
            result['accessibility_available'] = True
        except DesktopError as exc:
            result['accessibility_available'] = False
            result['accessibility_error'] = str(exc)
        except ValueError:
            result['accessibility_available'] = False
            result['accessibility_error'] = 'Accessibility provider returned an invalid application count.'
        result['session_state'] = session_state()
        result['keyboard'] = keyboard_capabilities()
        try:
            result['control'] = {'available':True, **self.control.status()}
        except DesktopError as exc:
            result['control'] = {'available':False, 'reason':exc.code}
        result['capabilities'] = capability_summary(result)
        result['capability_scope'] = 'Backend availability only; target focus, current input state and application support are checked per action.'
        result['ready'] = result['session_state']['input_ready'] is not False and all(dependencies.values()) and result['display_available'] and result['topology_available'] and result['session_bus'] and result['accessibility_available'] and result['keyboard']['available'] and result['control']['available']
        return result

    def active(self):
        try:
            return int(run(['xdotool','getactivewindow']).strip())
        except DesktopError:
            return None

    def list_windows(self):
        self.identity_epoch=getattr(self,'identity_epoch',None) or uuid.uuid4().hex
        for attempt in range(3):
            try:
                rows = run(['wmctrl','-lp']).decode(errors='replace').splitlines()
                break
            except DesktopError as exc:
                if exc.code == 'BACKEND_ERROR' and 'Cannot get client list properties' in str(exc):
                    self.windows = {}
                    self.window_diagnostics={'enumerated_count':0,'unavailable_count':0,'unavailable':[],'unavailable_truncated':False}
                    return []
                if exc.code == 'BACKEND_ERROR' and 'BadWindow' in str(exc) and 'X_GetProperty' in str(exc) and attempt<2:
                    # A dialog can disappear during wmctrl's read-only walk.
                    # Restart enumeration only; never retry a mutation.
                    time.sleep(.02)
                    continue
                raise
        active = self.active()
        parsed=[];unavailable=[]
        for row in rows:
            fields=row.split(None,4)
            try:
                if len(fields)<4:raise ValueError()
                xid,workspace,pid=int(fields[0],16),int(fields[1]),int(fields[2])
                if not 1<=xid<=0xffffffff or pid<=0:raise ValueError()
                parsed.append((xid,workspace,pid,fields[4][:512] if len(fields)>4 else ''))
            except ValueError:
                unavailable.append({'code':'UNAVAILABLE_WINDOW_OWNER'})
        metadata={}
        for offset in range(0,len(parsed),512):
            batch=self.display().window_metadata([row[0] for row in parsed[offset:offset+512]])
            metadata.update(batch['windows']);unavailable.extend(batch['unavailable'])
        result=[]
        for xid,workspace,pid,title in parsed:
            meta=metadata.get(xid)
            if meta is None:continue
            if meta['pid']!=pid:
                unavailable.append({'xid':xid,'code':'WINDOW_OWNER_CHANGED'})
                continue
            try:start=process_identity(pid)
            except DesktopError:
                unavailable.append({'xid':xid,'code':'STALE_TARGET'})
                continue
            bounds=meta['bounds'];frame=dict(bounds)
            extents=meta['frame_extents']
            if extents:
                frame={'x':bounds['x']-extents['left'],'y':bounds['y']-extents['top'],
                       'width':bounds['width']+extents['left']+extents['right'],
                       'height':bounds['height']+extents['top']+extents['bottom']}
            token=f"{self.identity_epoch}:{xid:x}:{pid}:{start}:{meta['generation']}"
            result.append({'window_id':token,'xid':xid,'pid':pid,'start':start,
                           'title':title,'workspace':workspace,'bounds':bounds,'frame_bounds':frame,
                           'active':xid==active,'wm_class':meta['wm_class'],
                           'unavailable_properties':meta['unavailable_properties']})
        self.windows={w['window_id']:w for w in result}
        self.window_diagnostics={'enumerated_count':len(rows),'unavailable_count':len(unavailable),
                                 'unavailable':unavailable[:100],'unavailable_truncated':len(unavailable)>100}
        return result

    def window_overview(self, query=None, limit=50, offset=0):
        if query is not None and (not isinstance(query,str) or len(query)>512):
            raise DesktopError('INVALID_ARGUMENT','query must be a string of at most 512 characters.')
        if type(limit) is not int or not 1<=limit<=200 or type(offset) is not int or not 0<=offset<=100000:
            raise DesktopError('INVALID_ARGUMENT','limit must be 1–200 and offset 0–100000.')
        windows=self.list_windows()
        if query is not None:
            needle=query.casefold()
            windows=[w for w in windows if needle in ' '.join([w['title'],*w['wm_class']]).casefold()]
        page=windows[offset:offset+limit];next_offset=offset+len(page)
        return {'windows':page,'total_matches':len(windows),'returned_count':len(page),
                'offset':offset,'truncated':next_offset<len(windows),
                'next_offset':next_offset if next_offset<len(windows) else None,
                **getattr(self,'window_diagnostics',{})}

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
        deadline = elapsed_time()+1.5
        while elapsed_time()<deadline:
            if self.active()==w['xid']:
                return {'effect':'verified','window_id':window_id,'verification':'active window matches'}
            time.sleep(.04)
        raise DesktopError('ACTIVATION_FAILED','Window did not become active.',effect='uncertain')

    def signature(self, windows):
        return [(w['window_id'], w['bounds'], w['active'], w['workspace']) for w in windows]

    @storage_errors('capture desktop screenshot')
    def observe(self, max_width=1280):
        if not 320 <= max_width <= 2560:
            raise DesktopError('INVALID_ARGUMENT','max_width must be 320–2560.')
        root = self.display().geometry(self.display().root)
        if root['width']<=0 or root['height']<=0 or root['width']*root['height']>32_000_000:
            raise DesktopError('SCREENSHOT_LIMIT','Desktop capture is limited to 32 million native pixels; reduce display resolution.')
        topology = self.display().topology()
        before = self.list_windows()
        before_popups = self.observe_popups(before)
        with tempfile.TemporaryDirectory(dir=self.runtime) as directory:
            path = str(Path(directory)/'screen.png')
            run(['scrot','--overwrite',path],timeout=4)
            try:
                with Image.open(path) as source:
                    native = source.size
                    if native!=(root['width'],root['height']):
                        raise DesktopError('DESKTOP_CHANGED','Display resolution changed during capture; observe again.')
                    scale = min(1,max_width/source.width,2560/source.height)
                    height = max(1,round(source.height*scale))
                    width = max(1,round(source.width*scale))
                    source = source.convert('RGB').resize((width,height),Image.Resampling.LANCZOS)
                    buf = io.BytesIO();source.save(buf,format='PNG')
            except (UnidentifiedImageError, Image.DecompressionBombError) as exc:
                raise DesktopError('SCREENSHOT_UNAVAILABLE','Capture did not produce a valid bounded image; no screenshot returned.') from exc
            except OSError as exc:
                if exc.errno is not None:raise  # Preserve storage/resource diagnostics.
                raise DesktopError('SCREENSHOT_UNAVAILABLE','Capture image could not be fully decoded; no screenshot returned.') from exc
        after = self.list_windows()
        after_popups = self.observe_popups(after)
        if topology != self.display().topology():
            raise DesktopError('DESKTOP_CHANGED','Display layout changed during capture; observe again.')
        if self.signature(before)!=self.signature(after) or self.popup_signature(before_popups)!=self.popup_signature(after_popups):
            raise DesktopError('DESKTOP_CHANGED','Window layout changed during capture; observe again.')
        token = uuid.uuid4().hex
        now = elapsed_time()
        self.snapshots = {k:v for k,v in self.snapshots.items() if now-v['time']<15}
        snapshot = {'time':now,'signature':self.signature(after),'native':native,'image':(width,height),'popups':after_popups,'topology':topology}
        self.snapshots[token] = snapshot
        while len(self.snapshots)>16:self.snapshots.pop(next(iter(self.snapshots)))
        return {'snapshot_id':token,'expires_after_seconds':15,
                'coordinate_space':'returned image pixels; pass snapshot_id with pointer actions',
                'coordinate_spaces':{'bounds':'native_x11_root_pixels','frame_bounds':'native_x11_root_pixels',
                                     'image_bounds':'returned_image_pixels','pointer':'returned_image_pixels'},
                'image_bounds_semantics':'Half-open rectangles of integer screenshot pixel positions; clipped to image, not an occlusion check.',
                'image_size':{'width':width,'height':height},
                'desktop_size':{'width':native[0],'height':native[1]},
                'display_topology':topology_summary(topology,(width,height)),
                'windows':[{**w,'image_bounds':image_bounds(w['bounds'],native,(width,height))} for w in after],
                'popups':[{**p,'image_bounds':image_bounds(p['bounds'],native,(width,height))} for p in after_popups],
                'image_base64':base64.b64encode(buf.getvalue()).decode()}

    def point(self, window_id, snapshot_id, x, y):
        return self._interaction_point(window_id,snapshot_id,x,y)

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
        window = self.target_window(window_id)
        target = window['xid']
        ready = self.pointer_readiness(snapshot_id,window)
        if kind=='click':
            click_button(buttons[button], count, target=target, position=(px,py), server_generation=ready['server_generation'],target_generation=ready['target_generation'])
        elif kind=='scroll':
            mapping={'up':'4','down':'5','left':'6','right':'7'}
            if direction not in mapping:
                raise DesktopError('INVALID_ARGUMENT','Invalid scroll direction.')
            click_button(mapping[direction], count, target=target, position=(px,py), server_generation=ready['server_generation'],target_generation=ready['target_generation'])
        elif kind=='drag':
            with held_button(buttons[button],target=target,position=(px,py),server_generation=ready['server_generation'],target_generation=ready['target_generation']) as pointer:
                for step in range(1,11):
                    ax=round(px+(end[0]-px)*step/10);ay=round(py+(end[1]-py)*step/10)
                    pointer.move(ax,ay);time.sleep(.02)
        return {'effect':'dispatched','verification':'Observe the resulting application state.'}

    def key(self, window_id, chord, count=1):
        validate_chord(chord)
        validate_key_count(count)
        target = self.target_window(window_id)
        return send_chord(chord, target['xid'], target_generation=target['window_id'].rsplit(':',1)[-1],count=count)

    def ax(self, request, mutating=False):
        worker = str(Path(__file__).with_name('ax_worker.py'))
        try:
            raw = run(['/usr/bin/python3',worker],data=json.dumps(request,ensure_ascii=False).encode(),timeout=5)
        except DesktopError as exc:
            if mutating and exc.code != 'DEPENDENCY_MISSING':
                exc.effect = 'uncertain'
                mark_effect()
            if request.get('op')=='secret':
                raise DesktopError(exc.code,'Protected input failed; inspect state before retrying.',effect=exc.effect) from exc
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
        now=elapsed_time()
        self.elements={k:v for k,v in self.elements.items() if now-v['time']<60}
        tokens = {node['path']:uuid.uuid4().hex for node in result['nodes']}
        for node in result['nodes']:
            token=tokens[node['path']]
            self.elements[token]={'time':now,'window_id':window_id,'node':dict(node)}
            node['element_id']=token
            node['parent_element_id']=tokens.get(node.pop('parent_path',None))
            node.pop('path',None);node.pop('start',None);node.pop('root_path',None);node.pop('name_fingerprint',None)
        while len(self.elements)>4000:self.elements.pop(next(iter(self.elements)))
        result['window_id']=window_id
        result['element_expiry_seconds']=60
        result['bounds_coordinate_space']='unavailable' if result.get('bounds_coordinates')=='unavailable' else 'native_x11_root_pixels'
        return result

    def element(self, element_id, op, **kwargs):
        target=self.elements.get(element_id)
        if not target or elapsed_time()-target['time']>=60:
            raise DesktopError('STALE_TARGET','Element expired or belongs to another server; inspect again.')
        w=self.target_window(target['window_id'],op!='read')
        node=target['node']
        if node['start']!=w['start']:
            raise DesktopError('STALE_TARGET','Process identity changed.')
        if op in ('set','insert','secret'):
            validate_text(kwargs['text'])
        return self.ax({'op':op,'pid':w['pid'],'start':w['start'],'target':node,**kwargs},op!='read')

    def type_text(self, element_id, text, mode='insert'):
        validate_text(text)
        if mode not in ('insert','replace'):
            raise DesktopError('INVALID_ARGUMENT','Text mode must be insert or replace.')
        target = self.elements.get(element_id)
        if not target or elapsed_time()-target['time']>=60:
            raise DesktopError('STALE_TARGET','Element expired; inspect again.')
        node = target['node']
        if node.get('protected'):
            raise DesktopError('PROTECTED_FIELD','Ordinary typing does not write protected fields.')
        if 'EditableText' in node['interfaces'] and node.get('native_text_mutation_supported',True):
            result = self.element(element_id,'insert' if mode=='insert' else 'set',text=text)
            if result.get('exact_match') is False:
                raise DesktopError('TEXT_MISMATCH','Application text does not match the requested result; inspect before retrying.',effect='uncertain',details={k:v for k,v in result.items() if k in ('actual_characters','expected_characters','caret_verified')})
            return result
        if 'Text' not in node['interfaces'] or 'editable' not in node['states']:
            raise DesktopError('NOT_EDITABLE','Target has no verifiable editable-text capability.')
        # Chromium exposes editable Text without EditableText. Use a verified
        # selection + clipboard transaction rather than requiring tool guessing.
        focused = self.element(element_id,'focus')
        if focused.get('effect')!='verified':
            raise DesktopError('FOCUS_UNVERIFIED','Cannot verify element focus; no text pasted.',effect=focused.get('effect','uncertain'))
        before = self.element(element_id,'read',limit=1_000_000)
        if not before.get('plain_text_verification_supported',True):
            raise DesktopError('TEXT_REPRESENTATION_UNSUPPORTED','The field exposes embedded objects rather than exact plain text. Use deliberate paste with application-specific verification.',details={'text_representation':before.get('text_representation'),'text_input_sent':False})
        if before['truncated']:
            raise DesktopError('VERIFICATION_LIMIT','Field exceeds exact readback budget; no text pasted.')
        selections = before.get('selections',[])
        if mode=='replace':
            start,end = 0,len(before['text'])
            selected = self.element(element_id,'select',start_offset=start,end_offset=end)
            if selected.get('effect')!='verified':
                raise DesktopError('SELECTION_UNVERIFIED','Cannot verify replacement selection; no text pasted.',effect='uncertain')
        elif len(selections)>1:
            raise DesktopError('UNSUPPORTED_SELECTION','Multiple text selections are not supported for insertion.')
        elif selections:
            start,end = selections[0]['start_offset'],selections[0]['end_offset']
        else:
            start=end=before.get('caret_offset',-1)
        if not 0 <= start <= end <= len(before['text']):
            raise DesktopError('INVALID_CARET','Target did not report a valid code-point caret/selection.')
        expected = before['text'][:start]+text+before['text'][end:]
        if len(expected)>1_000_000:
            raise DesktopError('VERIFICATION_LIMIT','Result would exceed exact readback budget.')
        current = self.element(element_id,'read',limit=1_000_000)
        actual_selections = current.get('selections',[])
        current_range = (actual_selections[0]['start_offset'],actual_selections[0]['end_offset']) if len(actual_selections)==1 else (current.get('caret_offset',-1),)*2 if not actual_selections else None
        if current['text']!=before['text'] or current_range!=(start,end):
            raise DesktopError('TEXT_CHANGED','Text or selection changed before paste; no text pasted.',effect='uncertain')
        if text=='':
            if start!=end:
                self.key(target['window_id'],'BackSpace')
        else:
            self.paste(target['window_id'],text)
        deadline=elapsed_time()+2
        while True:
            observed=self.element(element_id,'read',limit=1_000_000)
            if not observed.get('plain_text_verification_supported',True):
                raise DesktopError('TEXT_REPRESENTATION_UNSUPPORTED','Input was dispatched, but the resulting embedded-object representation cannot verify exact plain text. Inspect before retrying.',effect='uncertain',details={'text_representation':observed.get('text_representation'),'embedded_object_count':len(observed.get('embedded_objects',[]))})
            if not observed['truncated'] and observed['text']==expected:
                return {'effect':'verified','exact_match':True,'expected_characters':len(expected),
                        'actual_characters':len(observed['text']),'caret_verified':observed.get('caret_offset')==start+len(text),
                        'verification':'Exact destination text readback after clipboard insertion.'}
            if elapsed_time()>=deadline:
                raise DesktopError('TEXT_MISMATCH','Destination did not match requested text; inspect paste dialogs and contents before retrying.',effect='uncertain',details={'expected_characters':len(expected),'actual_characters':observed.get('characters')})
            time.sleep(.05)

    @storage_errors('prepare or dispatch clipboard paste', effect='uncertain')
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
        # Preserve the previous clipboard until the replacement is fully staged.
        with staged_payload(self.runtime, payload) as payload_path:
            if self.clipboard_owner:
                mark_effect();stop_process(self.clipboard_owner)
            mark_effect()
            try:
                self.clipboard_owner=subprocess.Popen(['xclip','-quiet','-selection','clipboard','-in',payload_path],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,env=subprocess_environment())
            except FileNotFoundError as exc:
                raise DesktopError('DEPENDENCY_MISSING', 'Missing executable: xclip', effect='uncertain') from exc
            deadline=elapsed_time()+1
            while True:
                try:
                    observed=run(['xclip','-selection','clipboard','-out'],timeout=.3)
                    if observed==payload:break
                except DesktopError as exc:
                    if exc.code in ('CANCELLED', 'TIMEOUT'):
                        checkpoint()
                checkpoint()
                if elapsed_time()>deadline:
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
        deadline = elapsed_time()+timeout
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
            remaining = deadline-elapsed_time()
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
                        lambda: self.admission.cancel() if getattr(self, 'admission', None) else None,
                        lambda: os.close(self.lockfd) if self.lockfd is not None else None):
            try:
                cleanup()
            except Exception as exc:
                errors.append(str(exc))
        for cache in ('snapshots', 'elements', 'windows'):
            getattr(self, cache, {}).clear()
        self.cleanup_errors = errors
