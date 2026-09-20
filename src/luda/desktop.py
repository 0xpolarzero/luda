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
from .fonts import font_coverage
from .ocr import recognize, retain_snapshot
from .recording import Recordings
from .browser import OwnedBrowser, capability as browser_capability
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
from .ime import composition_capability, native_text_readback
from .diagnostics import capability_summary
from .storage import storage_errors, staged_payload


class Desktop(InteractionMixin, ConditionWaitsMixin):
    browser_class = OwnedBrowser
    def __init__(self, environment=None):
        self.environment = MappingProxyType(dict(os.environ if environment is None else environment))
        self.identity_epoch = uuid.uuid4().hex
        self.x = None
        self.closed = False
        self._suspend_offset = suspend_offset()
        self.snapshots = {}
        self.elements = {}
        self.windows = {}
        from .window_history import WindowHistory
        self.window_history = WindowHistory()
        self.clipboard_owner = None
        self.recordings = Recordings(self)
        self.browser = self.browser_class(self)
        self.local_lock = threading.Lock()
        name = hashlib.sha256(display_identity(self.environment.get('DISPLAY','')).encode()).hexdigest()[:12]
        self.lockfd = None
        try:
            with storage_errors('initialize desktop runtime'):
                directory = Path(tempfile.gettempdir()) / f'luda-desktop-{os.getuid()}'
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

    @contextmanager
    def input_scope(self, window=None):
        """Choose compatibility before dispatch; nested actions keep that route."""
        target = window.get('window_id') if window else None
        if target is not None and getattr(self, '_input_window', None) == target:
            yield self._input_route
            return
        from .input_routing import prefers_private_input
        cached = getattr(self, '_private_windows', set())
        private = window is None or target in cached or prefers_private_input(window)
        environment = dict(self.environment)
        environment.pop('LUDA_PRIVATE_INPUT', None)
        environment['LUDA_INPUT_ROUTE'] = 'shared'
        if private:
            try:
                if getattr(self, 'private_input', None) is None:
                    from .private_input import PrivateInput
                    self.private_input = PrivateInput(self.environment)
                environment = self.private_input.environment()
                environment['LUDA_INPUT_ROUTE'] = 'private'
                if target is not None:
                    self._private_windows = cached | {target}
            except DesktopError as exc:
                if exc.code in ('CANCELLED', 'TIMEOUT', 'SESSION_CHANGED'):
                    raise
                # Startup failed before any application input. Compatibility
                # uses the normal foreground path, never a replayed mutation.
                checkpoint()
        route = environment['LUDA_INPUT_ROUTE']
        previous = (getattr(self, '_input_window', None), getattr(self, '_input_route', None))
        self._input_window, self._input_route = target, route
        try:
            with environment_scope(environment):
                yield route
        finally:
            self._input_window, self._input_route = previous

    def _activate_shared(self, window_id):
        """Foreground compatibility route, selected before application input."""
        window = self.target_window(window_id, False)
        state = keyboard_capabilities()
        if state.get('input_held') is True:
            raise DesktopError('INPUT_HELD', 'Release held keys or mouse buttons before foreground input.')
        if window.get('active'):
            return {'effect':'none', 'window_id':window_id}
        run(['xdotool','windowactivate',str(window['xid'])],effect='uncertain')
        deadline = elapsed_time()+1.5
        while elapsed_time()<deadline:
            try:
                current = self.target_window(window_id, False)
            except DesktopError as exc:
                exc.effect = 'uncertain'
                raise
            if current['active']:
                return {'effect':'verified','window_id':window_id,
                        'verification':'Foreground target identity and active window match.'}
            time.sleep(.04)
        raise DesktopError('ACTIVATION_FAILED','Window did not become active.',effect='uncertain')

    def check_input_focus(self,window):
        return self._input_focus(window,'check_focus')

    def focus_input(self,window):
        return self._input_focus(window,'focus')

    def _input_focus(self,window,operation):
        import sys
        request={'target':window['xid'],'target_generation':window['window_id'].rsplit(':',1)[-1]}
        result=json.loads(run([sys.executable,'-m','luda._keyboard_native',operation],
                             data=json.dumps(request).encode()+b'\n',timeout=2,max_output_bytes=4096,effect='uncertain' if operation=='focus' else 'none'))
        if result.get('code'):
            raise DesktopError(result['code'],result['message'],effect=result.get('effect','none'))
        return result

    def display(self):
        if self.x is None:
            self.x = X11()
        return self.x

    def require_supported_backend(self):
        # A fresh helper connection detects replacement by an unsupported server;
        # environment hints alone cannot identify Xwayland.
        if self.x is None:
            self.display()  # Construction already checks the current server.
        else:
            self.x.root

    def doctor(self):
        dependencies = {c: shutil.which(c, path=self.environment.get('PATH', os.defpath)) is not None for c in ('xdotool','wmctrl','scrot','xclip','xprop')}
        result = {'version':version('luda'),'backend':'X11 + AT-SPI','dependencies':dependencies,
                  'display':self.environment.get('DISPLAY'),'session_bus':bool(self.environment.get('DBUS_SESSION_BUS_ADDRESS')),
                  'uid':os.getuid(),'transport':'stdio','support':'experimental X11; Wayland unsupported',
                  'ime_composition':composition_capability(),
                  'owned_browser':browser_capability(self.environment),
                  'limitations':['Human viewer input is not locked out.','No automatic clipboard restoration.',
                                 'Accessibility mapping requires a uniquely identified application window.','No automatic retry of mutations.']}
        try:
            result['geometry'] = self.display().geometry(self.display().root)
            result['display_available'] = True
        except DesktopError as exc:
            result.update(display_available=False,display_error=str(exc),display_error_code=exc.code)
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
        result['font_coverage'] = font_coverage(self.environment)
        result['ocr'] = {'available': shutil.which('tesseract', path=self.environment.get('PATH', os.defpath)) is not None,
                         'engine': 'tesseract', 'scope': 'Optional executable availability only; requested language and recognition checked by desktop_ocr.'}
        result['recording'] = {'available': all(shutil.which(name,path=self.environment.get('PATH',os.defpath)) for name in ('ffmpeg','ffprobe')),
                               'scope':'Optional executables only; start validates capture support. No audio.'}
        result['session_state'] = session_state()
        try:
            with self.input_scope():result['keyboard'] = keyboard_capabilities()
        except DesktopError as exc:
            result['keyboard'] = {'available':False,'reason':exc.code}
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
        if getattr(self,'window_history',None) is not None:self.window_history.observe(result)
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
        if require_focus:
            self.check_input_focus(w)
        return w

    def activate(self, window_id):
        """Expose the target and focus only the agent's keyboard."""
        window = self.target_window(window_id, False)
        with self.input_scope(window) as route:
            if route == 'shared':
                return self._activate_shared(window_id)
            from .interaction import properties
            if '_NET_WM_STATE_HIDDEN' in properties(window['xid']):
                self.display().map_without_focus(window['xid'], window_id.rsplit(':', 1)[-1])
                window = self.target_window(window_id, False)
            raised = self._raise_window(window, window_id)
            if raised.get('effect') != 'verified':
                return raised
            try:
                self.focus_input(self.target_window(window_id, False))
            except DesktopError as exc:
                exc.effect = 'uncertain'
                raise
        return {'effect': 'verified', 'window_id': window_id,
                'verification': 'Window raised and agent keyboard focus verified.'}

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
        snapshot = {'time':now,'signature':self.signature(after),'native':native,'image':(width,height),'popups':after_popups,'topology':topology,'png':buf.getvalue()}
        retain_snapshot(self.snapshots, token, snapshot)
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

    def retained_snapshot(self, snapshot_id, *, current_layout=True):
        now = elapsed_time()
        for key in list(self.snapshots):
            if now-self.snapshots[key]['time'] >= 15:
                self.snapshots.pop(key)
        snapshot = self.snapshots.get(snapshot_id)
        if not snapshot or elapsed_time()-snapshot['time'] >= 15 or 'png' not in snapshot:
            raise DesktopError('STALE_OBSERVATION', 'Screenshot expired or was evicted; explicitly observe again.')
        if not current_layout:
            generation = snapshot['topology'].get('server_generation')
            if not generation or self.display().topology().get('server_generation') != generation:
                raise DesktopError('STALE_OBSERVATION', 'Template screenshot belongs to an unavailable server generation.')
            return snapshot
        windows = self.list_windows()
        if (self.signature(windows) != snapshot['signature']
                or self.display().topology() != snapshot['topology']
                or self.popup_signature(self.observe_popups(windows)) != self.popup_signature(snapshot['popups'])):
            raise DesktopError('STALE_OBSERVATION', 'Screenshot layout or server identity changed; explicitly observe again.')
        return snapshot

    def ocr(self, snapshot_id, language='eng', limit=200):
        def valid():
            return self.retained_snapshot(snapshot_id)
        snapshot = valid()
        result = recognize(snapshot['png'], snapshot['image'], language, limit, self.environment)
        valid()
        return {'snapshot_id': snapshot_id, 'effect': 'none', 'engine': 'tesseract', 'language': language,
                'source': 'retained screenshot; historical pixels, not a new capture or current text verification',
                'coordinate_space': 'returned screenshot image pixels',
                'image_size': dict(zip(('width', 'height'), snapshot['image'])),
                'confidence_semantics': 'Engine score 0–100; uncalibrated, not a probability or proof of exact text.',
                **result}

    def match_image(self, template_snapshot_id, template_bounds, snapshot_id, threshold=.95, limit=20):
        from .matching import match
        source = self.retained_snapshot(template_snapshot_id, current_layout=False)
        target = self.retained_snapshot(snapshot_id)
        result = match(source, target, template_bounds, threshold, limit)
        self.retained_snapshot(template_snapshot_id, current_layout=False)
        self.retained_snapshot(snapshot_id)
        return {'template_snapshot_id':template_snapshot_id, 'snapshot_id':snapshot_id,
                'template_bounds':template_bounds, 'effect':'none', 'engine':'opencv_TM_CCOEFF_NORMED',
                'threshold':threshold, 'coordinate_space':'target screenshot returned image pixels',
                'source':'Retained historical pixels only; no new capture, current-state verification or click authorization.',
                'score_semantics':'Uncalibrated normalized correlation; not a probability, semantic identity or exact color match.',
                'selection':'Score-ranked non-overlapping placements; overlapping candidates suppressed, at most limit+1 peak searches.',
                **result}

    def recording(self, action, recording_id=None, max_seconds=30):
        return self.recordings.action(action, recording_id, max_seconds)

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
        buttons = {'left':'1','middle':'2','right':'3'}
        if button not in buttons or not 1 <= count <= 20:
            raise DesktopError('INVALID_ARGUMENT','Invalid button or count.')
        points = [(window_id,x,y)] + ([(window_id,end_x,end_y)] if kind=='drag' else [])
        with self.pointer_action(window_id,snapshot_id,points) as routed:
            px,py = self.point(window_id,routed,x,y)
            end = self.point(window_id,routed,end_x,end_y) if kind=='drag' else None
            window = self.target_window(window_id)
            target = window['xid']
            ready = self.pointer_readiness(routed,window)
            self.agent_feedback(window_id,position=(px,py),kind=kind)
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
                        pointer.move(ax,ay)
                        self.agent_feedback(window_id,position=(ax,ay),kind='drag')
                        time.sleep(.02)
        return {'effect':'dispatched','verification':'Observe the resulting application state.'}

    @contextmanager
    def prepare_input_window(self, window_id, *, activate=True):
        """Use private focus where supported and foreground input otherwise."""
        target = self.target_window(window_id, False)
        with self.input_scope(target) as route:
            changed = False
            try:
                if activate:
                    if route == 'shared':
                        changed = self._activate_shared(window_id)['effect'] != 'none'
                        target = self.target_window(window_id, False)
                    else:
                        from .interaction import properties
                        if '_NET_WM_STATE_HIDDEN' in properties(target['xid']):
                            self.display().map_without_focus(target['xid'], window_id.rsplit(':', 1)[-1])
                            changed = True
                            target = self.target_window(window_id, False)
                    self.focus_input(target)
                    changed = True
                yield self.target_window(window_id)
            except DesktopError as exc:
                if changed and exc.effect == 'none':
                    exc.effect = 'uncertain'
                raise

    def key(self, window_id, chord, count=1, *, _activate=True):
        validate_chord(chord)
        validate_key_count(count)
        with self.prepare_input_window(window_id, activate=_activate) as target:
            feedback = getattr(self, 'agent_feedback', None)
            if feedback: feedback(window_id)
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
        from .progress import selection_progress
        progress=selection_progress(result.pop('progress',None)) if request.get('op')=='choose' and request.get('range_end') is not None else None
        if progress is not None:result['progress']=progress
        if 'error' in result:
            effect = result.get('effect', 'uncertain' if mutating and result['error']=='ACCESSIBILITY_ERROR' else 'none')
            mark_effect(effect)
            details = {'progress': progress} if progress is not None else {}
            if result['error'] == 'NOT_INTERACTABLE' and result.get('foreground_required') is True:
                details['foreground_required'] = True
            raise DesktopError(result['error'],result.get('message','Accessibility failed.'),effect=effect,details=details)
        if mutating:
            mark_effect(result.get('effect', 'dispatched'))
        return result

    def open_browser(self, url, lifetime):
        return self.browser.open(url, lifetime)

    def inspect(self, window_id, limit=150, name=None, role=None, states=None, max_depth=30):
        if not 1 <= limit <= 500:
            raise DesktopError('INVALID_ARGUMENT','limit must be 1–500.')
        w = self.target_window(window_id,False)
        owned = getattr(self, 'browser', None)
        browser_fields = None
        owned_unavailable = False
        if owned and owned.window_id == window_id:
            try:
                browser_fields = owned.inspect(window_id,limit,name,role,states)
            except DesktopError as exc:
                if exc.code != 'BROWSER_SCOPE_UNSUPPORTED':
                    raise
                # Optional page-field scope must not erase independently mapped
                # native accessibility. This changes observation only; cached
                # owned elements still route through their original provider.
                owned_unavailable = True
        try:
            result = self.ax({'op':'inspect','pid':w['pid'],'start':w['start'],'limit':limit,'bounds':w['bounds'],'frame_bounds':w['frame_bounds'],'window_title':w['title'],'filters':{k:v for k,v in {'name':name,'role':role,'states':states}.items() if v is not None},'max_depth':max_depth})
        except DesktopError as exc:
            if not browser_fields or exc.code not in ('ACCESSIBILITY_UNAVAILABLE','ACCESSIBILITY_ERROR'):
                raise
            result = {'nodes':[], 'accessibility_error':exc.code}
        if browser_fields is not None:
            # Put page fields before a potentially large browser-chrome tree.
            result = {'text_fields': browser_fields['fields'],
                      'text_fields_truncated': browser_fields['truncated'],
                      'owned_browser_limits': browser_fields['unsupported'], **result}
        if owned_unavailable:
            result = {'text_fields': [],
                      'owned_browser': {'available': False, 'code': 'BROWSER_SCOPE_UNSUPPORTED'},
                      **result}
        now=elapsed_time()
        self.elements={k:v for k,v in self.elements.items() if now-v['time']<60}
        tokens = {node['path']:uuid.uuid4().hex for node in result['nodes']}
        inspection_id=uuid.uuid4().hex
        for order,node in enumerate(result['nodes']):
            token=tokens[node['path']]
            self.elements[token]={'time':now,'window_id':window_id,'node':dict(node),'inspection_id':inspection_id,'inspection_order':order}
            node['element_id']=token
            node['parent_element_id']=tokens.get(node.pop('parent_path',None))
            node.pop('path',None);node.pop('start',None);node.pop('root_path',None);node.pop('root_provider',None);node.pop('root_bus_guid',None);node.pop('name_fingerprint',None)
        while len(self.elements)>4000:self.elements.pop(next(iter(self.elements)))
        result['window_id']=window_id
        result['element_expiry_seconds']=60
        result['bounds_coordinate_space']='unavailable' if result.get('bounds_coordinates')=='unavailable' else 'native_x11_root_pixels'
        return result

    def element(self, element_id, op, **kwargs):
        target=self.elements.get(element_id)
        if not target or elapsed_time()-target['time']>=60:
            raise DesktopError('STALE_TARGET','Element expired or belongs to another server; inspect again.')
        endpoint_id=kwargs.pop('range_end_id',None) if op=='choose' else None
        if endpoint_id is not None:
            end=self.elements.get(endpoint_id) if isinstance(endpoint_id,str) else None
            if not end or elapsed_time()-end['time']>=60:
                raise DesktopError('STALE_TARGET','Range endpoint expired; inspect the complete range again.')
            if target.get('provider')=='owned_browser' or end.get('provider')=='owned_browser':
                raise DesktopError('UNSUPPORTED_ACTION','Range selection supports native list/table collections only.')
            if not target.get('inspection_id') or end.get('inspection_id')!=target['inspection_id'] or end['window_id']!=target['window_id']:
                raise DesktopError('STALE_TARGET','Range endpoints must come from the same inspection and window.')
            lo,hi=sorted((target['inspection_order'],end['inspection_order']))
            observed=sorted((v for v in self.elements.values() if v.get('inspection_id')==target['inspection_id'] and lo<=v['inspection_order']<=hi),key=lambda v:v['inspection_order'])
            kwargs['range_end']=end['node'];kwargs['range_nodes']=[v['node'] for v in observed]
        if target.get('provider') == 'owned_browser':
            if op=='secret':validate_text(kwargs['text'])
            return self.browser.element(target,op,**kwargs)
        w=self.target_window(target['window_id'],False)
        node=target['node']
        if node['start']!=w['start']:
            raise DesktopError('STALE_TARGET','Process identity changed.')
        if op == 'invoke':
            actions = node.get('actions', [])
            action = kwargs.get('action')
            if action is None:
                if not actions:
                    raise DesktopError('UNSUPPORTED_ACTION','This element exposes no action; inspect another control or use screenshot input.')
                if len(actions) != 1:
                    raise DesktopError('ACTION_REQUIRED','This element exposes several actions; choose an exact action from desktop_inspect.',details={'actions':actions})
                action = actions[0]
            if not isinstance(action,str) or action not in actions:
                raise DesktopError('UNSUPPORTED_ACTION','Choose an exact action returned by desktop_inspect.')
            kwargs['action'] = action
        if op in ('set','insert','secret'):
            validate_text(kwargs['text'])
        if op == 'focus':
            if 'Component' not in node.get('interfaces', []):
                raise DesktopError('UNSUPPORTED','Element has no Component interface.')
        def dispatch(window):
            if op != 'read':
                feedback = getattr(self, 'agent_feedback', None)
                if feedback: feedback(target['window_id'], element_id=element_id)
            return self.ax({'op':op,'pid':window['pid'],'start':window['start'],'target':node,**kwargs},op!='read')

        if op == 'focus':
            with self.prepare_input_window(target['window_id']) as current:
                result = dispatch(current)
        else:
            try:
                result = dispatch(w)
            except DesktopError as exc:
                # Only a provider refusal proven to precede mutation permits a
                # single foreground retry. Never replay uncertain app effects.
                if (op == 'read' or w.get('active') is not False or exc.effect != 'none'
                        or not (exc.code == 'FOCUS_CHANGED' or
                                (exc.code == 'NOT_INTERACTABLE' and exc.details.get('foreground_required') is True))):
                    raise
                self.activate(target['window_id'])
                with self.prepare_input_window(target['window_id']) as current:
                    result = dispatch(current)
        return native_text_readback(result) if op in ('read','set','insert') else result

    def type_text(self, element_id, text, mode='insert'):
        validate_text(text)
        if mode not in ('insert','replace'):
            raise DesktopError('INVALID_ARGUMENT','Text mode must be insert or replace.')
        target = self.elements.get(element_id)
        if not target or elapsed_time()-target['time']>=60:
            raise DesktopError('STALE_TARGET','Element expired; inspect again.')
        if target.get('provider') == 'owned_browser':
            return self.browser.element(target,'type',text=text,mode=mode)
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
                self.key(target['window_id'],'BackSpace', _activate=False)
        else:
            self.paste(target['window_id'],text, _activate=False)
        deadline=elapsed_time()+2
        while True:
            observed=self.element(element_id,'read',limit=1_000_000)
            if not observed.get('plain_text_verification_supported',True):
                raise DesktopError('TEXT_REPRESENTATION_UNSUPPORTED','Input was dispatched, but the resulting embedded-object representation cannot verify exact plain text. Inspect before retrying.',effect='uncertain',details={'text_representation':observed.get('text_representation'),'embedded_object_count':len(observed.get('embedded_objects',[]))})
            if not observed['truncated'] and observed['text']==expected:
                return native_text_readback({'effect':'verified','exact_match':True,'expected_characters':len(expected),
                        'actual_characters':len(observed['text']),'caret_verified':observed.get('caret_offset')==start+len(text)})
            if elapsed_time()>=deadline:
                raise DesktopError('TEXT_MISMATCH','Destination did not match requested text; inspect paste dialogs and contents before retrying.',effect='uncertain',details={'expected_characters':len(expected),'actual_characters':observed.get('characters')})
            time.sleep(.05)

    @storage_errors('prepare or dispatch clipboard paste', effect='uncertain')
    def paste(self, window_id, text, shortcut=None, *, _activate=True):
        validate_text(text)
        target = self.target_window(window_id, False)
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
        with self.prepare_input_window(window_id, activate=_activate):
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
            # Recheck focus after preparing clipboard. Do not reacquire a window
            # that lost focus during this transaction: its intended field may differ.
            try:
                self.target_window(window_id)
                if self.clipboard_owner.poll() is not None or run(['xclip','-selection','clipboard','-out'],timeout=.5) != payload:
                    raise DesktopError('CLIPBOARD_CHANGED', 'Clipboard ownership or contents changed before paste; no shortcut sent.', effect='uncertain')
                self.key(window_id, chords[shortcut], _activate=False)
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
        for cleanup in (lambda: self.cursor.close() if getattr(self, 'cursor', None) else None,
                        lambda: self.browser.close() if hasattr(self, 'browser') else None,
                        lambda: self.recordings.close() if hasattr(self, 'recordings') else None,
                        lambda: self.private_input.close() if getattr(self, 'private_input', None) else None,
                        lambda: stop_process(self.clipboard_owner) if self.clipboard_owner else None,
                        lambda: self.x.close() if self.x else None,
                        lambda: self.admission.cancel() if getattr(self, 'admission', None) else None,
                        lambda: os.close(self.lockfd) if self.lockfd is not None else None):
            try:
                cleanup()
            except Exception as exc:
                errors.append(str(exc))
        if getattr(self,'window_history',None) is not None:self.window_history.clear()
        for cache in ('snapshots', 'elements', 'windows'):
            getattr(self, cache, {}).clear()
        self.cleanup_errors = errors
