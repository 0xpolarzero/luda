"""Window-manager and pointer operations; caller holds Desktop.transaction()."""
import math
import json
import time
import uuid
from pathlib import Path
from contextlib import contextmanager
from .common import DesktopError, process_identity, run
from .timing import elapsed_time
from .window_history import WindowHistory, geometry, normal
from .input_guard import held_button
from .pointer_input import click_button, check_pointer_ready, move_pointer


def integer(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise DesktopError('INVALID_ARGUMENT', f'{name} must be an integer from {low} to {high}.')
    return value


def properties(xid, include_hints=False):
    return run(['xprop', '-id', str(xid), '_NET_WM_STATE', *(['WM_NORMAL_HINTS'] if include_hints else [])]).decode(errors='replace')


class InteractionMixin:
    """Public operations use existing opaque window/screenshot identities."""
    def agent_feedback(self, window_id, *, element_id=None, position=None, kind='action'):
        """Best-effort visual feedback; never another input device or tool."""
        if not getattr(self, 'environment', {}).get('DISPLAY'):
            return
        try:
            if position is None:
                window = self.target_window(window_id, False)
                bounds = window['bounds']
                target = getattr(self, 'elements', {}).get(element_id, {})
                if target.get('node') and target.get('provider') != 'owned_browser':
                    # Never put the cursor at stale inspection coordinates after
                    # a scroll, resize or layout change. This read has its own
                    # short budget; missing geometry degrades to a window marker.
                    try:
                        raw = run(['/usr/bin/python3', str(Path(__file__).with_name('ax_worker.py'))],
                                  data=json.dumps({'op':'locate','pid':window['pid'],'start':window['start'],
                                                   'target':target['node']}).encode(),
                                  timeout=.4, max_output_bytes=4096)
                        bounds = json.loads(raw).get('bounds') or bounds
                    except Exception:
                        pass
                position = (bounds['x'] + bounds['width']//2, bounds['y'] + bounds['height']//2)
            if getattr(self, 'cursor', None) is None:
                from .cursor import Cursor
                self.cursor = Cursor(environment=self.environment)
            self.cursor.show(*position, kind=kind)
        except Exception:
            # Visual feedback must never turn a dispatched action into a retry.
            pass

    @contextmanager
    def pointer_action(self, window_id, snapshot_id, points, popup_id=None):
        """Route validated visible pixels through the agent's private devices.

        Device focus can update a toolkit's active-window bookkeeping. Permit
        that transition only; geometry, coverage and popup identity stay checked.
        """
        cursor = getattr(self, 'cursor', None)
        if cursor is not None:
            cursor.hide()
        window = self.target_window(window_id, False)
        for target, x, y in points:
            if popup_id is not None:
                self._popup_point(target, popup_id, snapshot_id, x, y, False)
            else:
                self._interaction_point(target, snapshot_id, x, y, False)
        snap = self.snapshots[snapshot_id]
        with self.input_scope(window) as route:
            ready = check_pointer_ready()
            if ready['server_generation'] != snap.get('topology', {}).get('server_generation'):
                raise DesktopError('STALE_OBSERVATION', 'X server changed after observation; observe again.')
            token = None
            focused = False
            try:
                if route == 'shared':
                    self._activate_shared(window_id)
                self.focus_input(window)
                focused = True
                current = self.list_windows()
                def layout(signature):
                    return {row[0]: (row[1], row[3]) for row in signature}
                signature = self.signature(current)
                if layout(signature) != layout(snap['signature']):
                    raise DesktopError('STALE_OBSERVATION', 'Window layout changed during agent focus; observe again.')
                if self.display().topology() != snap.get('topology'):
                    raise DesktopError('STALE_OBSERVATION', 'Desktop changed during agent focus; observe again.')
                if self.popup_signature(self.observe_popups(current)) != self.popup_signature(snap.get('popups', [])):
                    raise DesktopError('STALE_OBSERVATION', 'Popup layout changed during agent focus; observe again.')
                token = uuid.uuid4().hex
                self.snapshots[token] = {**snap, 'signature': signature}
                yield token
            except DesktopError as exc:
                if focused and exc.effect == 'none':
                    exc.effect = 'uncertain'
                    exc.details['prior_effects_possible'] = True
                raise
            finally:
                if token is not None:
                    self.snapshots.pop(token, None)

    def pointer_readiness(self, snapshot_id, window):
        identity=window['window_id'].rsplit(':',1)[-1]
        ready=check_pointer_ready(window['xid'],target_generation=identity)
        observed=self.snapshots.get(snapshot_id,{}).get('topology',{}).get('server_generation')
        if not observed or ready['server_generation']!=observed:
            raise DesktopError('STALE_OBSERVATION','X server changed after observation; observe again.')
        return {**ready,'target_generation':identity}

    def workspaces(self):
        result = []
        for row in run(['wmctrl', '-d']).decode(errors='replace').splitlines():
            fields = row.split(None, 9)
            if len(fields) >= 9:
                result.append({'workspace': int(fields[0]), 'active': fields[1] == '*',
                               'name': fields[9] if len(fields) > 9 else ''})
        return result

    def _workspace(self, workspace):
        integer(workspace, 'workspace', 0, 4095)
        if workspace not in [w['workspace'] for w in self.workspaces()]:
            raise DesktopError('INVALID_ARGUMENT', 'Workspace does not exist; list workspaces first.')

    def switch_workspace(self, workspace):
        self._workspace(workspace)
        # Even an unchanged request is dispatched. Its outcome may be uncertain,
        # and a sticky active window can leave the normal layout signature equal.
        snapshots=getattr(self,'snapshots',{})
        invalidated=len(snapshots)
        snapshots.clear()
        run(['wmctrl', '-s', str(workspace)], effect='uncertain')
        return self._await_state(lambda: any(w['workspace'] == workspace and w['active'] for w in self.workspaces()),
                                 {'workspace': workspace, 'screenshot_ids_invalidated':invalidated})

    def _await_state(self, predicate, extra):
        deadline = time.monotonic() + 1.5
        while True:
            if predicate():
                return {'effect': 'verified', 'verification': 'Window-manager state matches request.', **extra}
            if time.monotonic() >= deadline:
                return {'effect': 'dispatched', 'verification': 'Requested state was not observed; inspect before retrying.', **extra}
            time.sleep(.04)

    def manage_window(self, window_id, action, x=None, y=None, width=None, height=None, workspace=None):
        actions = {'move', 'resize', 'maximize', 'minimize', 'fullscreen', 'raise', 'restore', 'close', 'workspace'}
        if action not in actions:
            raise DesktopError('INVALID_ARGUMENT', 'Unknown window action.')
        supplied = {k for k,v in {'x':x,'y':y,'width':width,'height':height,'workspace':workspace}.items() if v is not None}
        required = {'move': {'x','y'}, 'resize': {'width','height'}, 'workspace': {'workspace'}}.get(action, set())
        if supplied != required:
            raise DesktopError('INVALID_ARGUMENT', f'{action} requires exactly these parameters: {sorted(required)}.')
        if action == 'move':
            integer(x, 'x', -32768, 32767); integer(y, 'y', -32768, 32767)
        if action == 'resize':
            integer(width, 'width', 1, 32767); integer(height, 'height', 1, 32767)
        if action == 'workspace': self._workspace(workspace)
        w = self.target_window(window_id, False)
        xid = str(w['xid'])
        history=getattr(self,'window_history',None)
        if history is None:self.window_history=history=WindowHistory()
        reference=None;before=None;before_state='';stable=False
        if action in ('maximize','restore'):
            previous=history.take(window_id)
            try:
                before_state=properties(w['xid'],include_hints=True)
                before=self.target_window(window_id,False)
                stable=geometry(w)==geometry(before)
                reference=history.context(before,before_state,previous,stable)
            except DesktopError as exc:
                if exc.code in ('CANCELLED','TIMEOUT','STALE_TARGET'):raise
                reference={'reason':'pre_action_metadata_unavailable'}
        elif action!='raise':history.invalidate(window_id)
        if action == 'raise':return self._raise_window(w,window_id)
        if action == 'move': command = ['wmctrl','-ir',xid,'-e',f'0,{x},{y},-1,-1']
        elif action == 'resize': command = ['xdotool','windowsize',xid,str(width),str(height)]
        elif action == 'minimize': command = ['xdotool','windowminimize',xid]
        elif action == 'fullscreen': command = ['wmctrl','-ir',xid,'-b','add,fullscreen']
        elif action == 'close': command = ['wmctrl','-ic',xid]
        elif action == 'workspace': command = ['wmctrl','-ir',xid,'-t',str(workspace)]
        else: command = ['wmctrl','-ir',xid,'-b',('add' if action == 'maximize' else 'remove')+',maximized_vert,maximized_horz']
        run(command, effect='uncertain')
        if action == 'restore':
            run(['wmctrl','-ir',xid,'-b','remove,fullscreen'],effect='uncertain')
            if '_NET_WM_STATE_HIDDEN' in before_state:
                self.display().map_without_focus(w['xid'], window_id.rsplit(':', 1)[-1])
        dialogs=[]
        def matches():
            current = next((v for v in self.list_windows() if v['window_id'] == window_id), None)
            if action == 'close':
                if current is None:return True
                for candidate in self.windows.values():
                    if candidate['window_id']==window_id or not w.get('pid') or candidate.get('pid')!=w['pid']:continue
                    if self.display().transient_for(candidate['xid'])==w['xid'] and '_NET_WM_STATE_MODAL' in properties(candidate['xid']):
                        dialogs.append(candidate['window_id'])
                return bool(dialogs)
            if current is None: return False
            if action == 'move': return all(current['frame_bounds'][key] == value for key,value in [('x',x),('y',y)])
            if action == 'resize': return current['bounds']['width'] == width and current['bounds']['height'] == height
            if action == 'workspace': return current['workspace'] == workspace
            state = properties(current['xid'])
            if action == 'fullscreen': return '_NET_WM_STATE_FULLSCREEN' in state
            if action == 'minimize': return '_NET_WM_STATE_HIDDEN' in state
            maximized = all('_NET_WM_STATE_MAXIMIZED_'+part in state for part in ('VERT','HORZ'))
            if action == 'maximize': return maximized
            return not any(token in state for token in ('_NET_WM_STATE_HIDDEN','_NET_WM_STATE_MAXIMIZED_VERT','_NET_WM_STATE_MAXIMIZED_HORZ','_NET_WM_STATE_FULLSCREEN'))
        result=self._await_state(matches, {'window_id':window_id,'action':action})
        if action=='close':
            if dialogs:
                result.update(effect='dispatched',outcome='blocked_by_dialog',dialog_window_ids=dialogs,verification='Owner remains open with an owned modal dialog. Inspect it; no dialog was confirmed.')
            else:result['outcome']='closed' if result['effect']=='verified' else 'still_open'
        if action in {'move','resize','maximize','restore','fullscreen','minimize'}:
            # State property reads and enumeration are separate X11 requests.
            # Revalidate the complete native generation after the property read;
            # never attach replacement-window measurements to this action.
            try:
                current=self.target_window(window_id,False)
                state=properties(current['xid'],include_hints=action in ('maximize','restore'))
                current=self.target_window(window_id,False)
            except DesktopError as exc:
                raise DesktopError(exc.code, 'Window measurements became unavailable after dispatch; list windows again.', effect='uncertain') from exc
            observed={'client_bounds':dict(current['bounds']),
                      'frame_bounds':dict(current['frame_bounds']),
                      'wm_state':{name:token in state for name,token in (
                          ('maximized_vertical','_NET_WM_STATE_MAXIMIZED_VERT'),
                          ('maximized_horizontal','_NET_WM_STATE_MAXIMIZED_HORZ'),
                          ('fullscreen','_NET_WM_STATE_FULLSCREEN'),
                          ('hidden','_NET_WM_STATE_HIDDEN'))},
                      'scope':'Post-dispatch same-generation observations; separate X11 reads, not an atomic snapshot.'}
            if action in {'move','resize'}:
                requested={'x':x,'y':y} if action=='move' else {'width':width,'height':height}
                basis='frame_bounds' if action=='move' else 'client_bounds'
                matched=all(observed[basis][key]==value for key,value in requested.items())
                observed.update(requested=requested,requested_basis=basis,
                                request_match='matched' if matched else 'nonmatching',
                                constraint_reason='not_determined')
                # A later observation cannot upgrade a timed-out dispatch, but
                # it can disprove a match seen by the earlier polling loop.
                if not matched and result['effect']=='verified':
                    result.update(effect='dispatched',verification='Requested geometry no longer matches the latest observation; inspect before retrying.')
            else:
                flags=observed['wm_state']
                matched=({'maximize':flags['maximized_vertical'] and flags['maximized_horizontal'],
                          'restore':not any(flags.values()),'fullscreen':flags['fullscreen'],
                          'minimize':flags['hidden']})[action]
                if not matched and result['effect']=='verified':
                    result.update(effect='dispatched',verification='Requested WM state no longer matches the latest observation; inspect before retrying.')
            if action=='maximize':
                if before is not None and normal(before_state):
                    history.capture(window_id,before,before_state,current,state,stable)
                elif before is not None:
                    history.put(window_id,history.context(current,state,reference))
                else:history.put(window_id,reference)
                observed['restore_reference']={'status':'captured' if not history.entries[window_id].get('reason') else 'unknown'}
                if history.entries[window_id].get('reason'):observed['restore_reference']['reason']=history.entries[window_id]['reason']
            elif action=='restore':
                observed['restore_comparison']=history.compare(reference,current,state)
            result['observed_geometry']=observed
        return result

    def _raise_window(self, window, window_id):
        frame=self.display().root_surface(window['xid'])
        if frame is None:raise DesktopError('STALE_TARGET','Window frame disappeared before raising.')
        def stacking():
            return self.display().children(self.display().root)
        def layer(xid):
            state=run(['xprop','-id',str(xid),'_NET_WM_STATE','_NET_WM_WINDOW_TYPE']).decode(errors='replace')
            excluded=any(token in state for token in ('_NET_WM_STATE_HIDDEN','_NET_WM_WINDOW_TYPE_DOCK','_NET_WM_WINDOW_TYPE_DESKTOP'))
            flags=tuple(token in state for token in ('_NET_WM_STATE_ABOVE','_NET_WM_STATE_BELOW','_NET_WM_STATE_FULLSCREEN'))
            return excluded,flags
        before=stacking()
        if frame not in before:
            raise DesktopError('UNSUPPORTED','Window manager does not expose this window in its stacking order.')
        hidden,target_layer=layer(window['xid'])
        if hidden:raise DesktopError('NOT_INTERACTABLE','Raise requires a visible application window; restore it first.')
        visible_workspaces={-1,window['workspace']}
        if window['workspace']==-1:
            current=next((w['workspace'] for w in self.workspaces() if w['active']),None)
            if current is None:raise DesktopError('UNSUPPORTED','Cannot resolve the current workspace for a sticky window.')
            visible_workspaces.add(current)
        focus=self.active()
        peers=[]
        for other in self.windows.values():
            if other['xid']==window['xid'] or other['workspace'] not in visible_workspaces:continue
            excluded,other_layer=layer(other['xid'])
            if not excluded and other_layer==target_layer:
                other_frame=self.display().root_surface(other['xid'])
                if other_frame in before:peers.append((before.index(other_frame),other['xid']))
        # Explicit sibling avoids XFWM's activate-on-unspecified-raise policy.
        # Already-topmost windows require no mutation, including no focus request.
        if peers and max(peers)[0]>before.index(frame):
            self.display().restack_above(window['xid'],max(peers)[1])
        def raised():
            if self.active()!=focus:
                raise DesktopError('FOCUS_CHANGED','Focus changed while raising. Inspect before continuing.',effect='uncertain')
            windows=self.list_windows()
            if not any(w['window_id']==window_id for w in windows):
                raise DesktopError('STALE_TARGET','Window disappeared while raising.',effect='uncertain')
            order=stacking()
            if frame not in order or self.display().root_surface(window['xid'])!=frame:return False
            for other in windows:
                if other['xid']==window['xid'] or other['workspace'] not in visible_workspaces:continue
                excluded,other_layer=layer(other['xid'])
                if not excluded and other_layer==target_layer:
                    other_frame=self.display().root_surface(other['xid'])
                    if other_frame in order and order.index(other_frame)>order.index(frame):return False
            return self.active()==focus
        result=self._await_state(raised,{'window_id':window_id,'action':'raise'})
        if result['effect']=='verified':
            result['verification']='Window is above visible peers in its stacking layer; active window stayed unchanged.'
        return result

    def _interaction_point(self, window_id, snapshot_id, x, y, require_focus=True):
        if any(isinstance(v, bool) or not isinstance(v, (int,float)) or not math.isfinite(v) for v in (x,y)):
            raise DesktopError('INVALID_ARGUMENT', 'Coordinates must be finite numbers.')
        snap = self.snapshots.get(snapshot_id)
        if not snap or elapsed_time()-snap['time'] >= 15:
            raise DesktopError('STALE_OBSERVATION', 'Screenshot expired; observe again.')
        w = self.target_window(window_id, require_focus)
        if self.signature(list(self.windows.values())) != snap['signature']:
            raise DesktopError('STALE_OBSERVATION', 'Window layout or focus changed; observe again.')
        root = self.display().geometry(self.display().root)
        if (root['width'],root['height']) != tuple(snap['native']):
            raise DesktopError('STALE_OBSERVATION', 'Display resolution changed; observe again.')
        if self.display().topology() != snap.get('topology'):
            raise DesktopError('STALE_OBSERVATION', 'Display layout or X server changed; observe again.')
        iw,ih = snap['image']; nw,nh = snap['native']
        if not 0 <= x < iw or not 0 <= y < ih:
            raise DesktopError('OUT_OF_BOUNDS', 'Point is outside screenshot.')
        px,py = int(x*nw/iw),int(y*nh/ih)
        # An owned menu is part of its window's interaction surface. Agents use
        # the same image coordinates and owner window ID for menus and clients.
        for popup in reversed(snap.get('popups',[])):
            b = popup['bounds']
            if popup['owner_window_id']==window_id and b['x']<=px<b['x']+b['width'] and b['y']<=py<b['y']+b['height']:
                return self._popup_point(window_id,popup['popup_id'],snapshot_id,x,y,require_focus)
        if self.display().surface_at(px,py)!=self.display().root_surface(w['xid']):
            raise DesktopError('OCCLUDED_TARGET','Another surface covers this point; observe again.')
        b = w['bounds']
        if not b['x'] <= px < b['x']+b['width'] or not b['y'] <= py < b['y']+b['height']:
            raise DesktopError('OUT_OF_BOUNDS', 'Point is outside target client bounds.')
        return px,py

    def hover(self, window_id, snapshot_id, x, y):
        with self.pointer_action(window_id,snapshot_id,[(window_id,x,y)]) as routed:
            px,py = self._interaction_point(window_id,routed,x,y)
            window=self.target_window(window_id)
            ready=self.pointer_readiness(routed,window)
            self.agent_feedback(window_id,position=(px,py),kind='move')
            move_pointer(px,py,ready['server_generation'],target=window['xid'],target_generation=ready['target_generation'])
        return {'effect':'dispatched','verification':'Pointer motion sent; observe tooltips or hover state.'}

    def drag_between(self, source_window_id, target_window_id, snapshot_id, x, y, end_x, end_y, button='left'):
        buttons = {'left':'1','middle':'2','right':'3'}
        if button not in buttons: raise DesktopError('INVALID_ARGUMENT','Unknown mouse button.')
        with self.pointer_action(source_window_id,snapshot_id,[(source_window_id,x,y),(target_window_id,end_x,end_y)]) as routed:
            start = self._interaction_point(source_window_id,routed,x,y)
            end = self._interaction_point(target_window_id,routed,end_x,end_y,False)
            window=self.target_window(source_window_id)
            ready=self.pointer_readiness(routed,window)
            self.agent_feedback(source_window_id,position=start,kind='drag')
            with held_button(buttons[button],target=window['xid'],position=start,server_generation=ready['server_generation'],target_generation=ready['target_generation']) as pointer:
                for step in range(1,16):
                    p = [round(start[i]+(end[i]-start[i])*step/15) for i in (0,1)]
                    pointer.move(p[0],p[1])
                    self.agent_feedback(source_window_id,position=p,kind='drag')
                    time.sleep(.02)
        return {'effect':'dispatched','verification':'Drag input sent and button released; inspect both applications to verify transfer.'}

    @staticmethod
    def popup_signature(popups):
        return [(p['xid'],p['generation'],p['pid'],p['start'],p['owner_window_id'],p['transient_for'],p['bounds']) for p in popups]

    def observe_popups(self, windows=None):
        """Only mapped surfaces linked by ICCCM owner hints to a live window.

        A matching process alone is insufficient: one app can own many windows.
        Tokens authorize only the snapshot in which they were issued.
        """
        if windows is None: windows=self.list_windows()
        raw=self.display().popup_surfaces()
        generations=self.display().window_tokens([p['xid'] for p in raw])
        surfaces={p['xid']:p for p in raw}
        owners={w['xid']:w for w in windows}
        result=[]
        for popup in raw:
            if popup['xid'] not in generations:continue
            owner=None; current=popup; visited=set()
            for _ in range(16):
                if current['xid'] in visited:break
                visited.add(current['xid'])
                parent=current.get('transient_for')
                if parent in owners:
                    owner=owners[parent];break
                current=surfaces.get(parent)
                if current is None or current.get('pid')!=popup.get('pid'):break
            if owner is None or popup.get('pid')!=owner['pid']:continue
            try:
                start=process_identity(popup['pid'])
            except DesktopError:continue
            if start!=owner['start']:continue
            result.append({**popup,'bounds':dict(popup['bounds']),'start':start,'generation':generations[popup['xid']],'owner_window_id':owner['window_id'],'popup_id':uuid.uuid4().hex})
        return result

    def _popup_point(self, owner_window_id, popup_id, snapshot_id, x, y, require_focus=True):
        if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in (x,y)):
            raise DesktopError('INVALID_ARGUMENT','Coordinates must be finite numbers.')
        snap=self.snapshots.get(snapshot_id)
        if not snap or elapsed_time()-snap['time']>=15:
            raise DesktopError('STALE_OBSERVATION','Screenshot expired; observe again.')
        observed=next((p for p in snap.get('popups',[]) if p['popup_id']==popup_id and p['owner_window_id']==owner_window_id),None)
        if observed is None:raise DesktopError('STALE_TARGET','Popup is not authorized by this screenshot and owner.')
        self.target_window(owner_window_id,require_focus)
        if self.signature(list(self.windows.values()))!=snap['signature']:
            raise DesktopError('STALE_OBSERVATION','Window layout or focus changed; observe again.')
        current=self.observe_popups(list(self.windows.values()))
        if self.popup_signature(current)!=self.popup_signature(snap['popups']):
            raise DesktopError('STALE_OBSERVATION','Popup layout or ownership changed; observe again.')
        root=self.display().geometry(self.display().root)
        if (root['width'],root['height'])!=tuple(snap['native']):
            raise DesktopError('STALE_OBSERVATION','Display resolution changed; observe again.')
        if self.display().topology() != snap.get('topology'):
            raise DesktopError('STALE_OBSERVATION', 'Display layout or X server changed; observe again.')
        iw,ih=snap['image'];nw,nh=snap['native']
        if not 0<=x<iw or not 0<=y<ih:raise DesktopError('OUT_OF_BOUNDS','Point is outside screenshot.')
        px,py=int(x*nw/iw),int(y*nh/ih);b=observed['bounds']
        if not b['x']<=px<b['x']+b['width'] or not b['y']<=py<b['y']+b['height']:
            raise DesktopError('OUT_OF_BOUNDS','Point is outside popup bounds.')
        if self.display().surface_at(px,py)!=observed['xid']:
            raise DesktopError('OCCLUDED_TARGET','Another surface covers this popup point; observe again.')
        return px,py

    def pointer_popup(self, owner_window_id, popup_id, snapshot_id, x, y, kind='click', button='left', count=1, direction='down'):
        if kind not in {'click','hover','scroll'}:
            raise DesktopError('INVALID_ARGUMENT','Popup pointer kind must be click, hover or scroll.')
        buttons={'left':'1','middle':'2','right':'3'}
        directions={'up':'4','down':'5','left':'6','right':'7'}
        integer(count,'count',1,20)
        if button not in buttons or direction not in directions:
            raise DesktopError('INVALID_ARGUMENT','Unknown pointer button or scroll direction.')
        with self.pointer_action(owner_window_id,snapshot_id,[(owner_window_id,x,y)],popup_id) as routed:
            px,py=self._popup_point(owner_window_id,popup_id,routed,x,y)
            window=self.target_window(owner_window_id)
            ready=self.pointer_readiness(routed,window)
            self.agent_feedback(owner_window_id,position=(px,py),kind=kind)
            if kind!='hover':
                click_button(buttons[button] if kind=='click' else directions[direction],count,target=window['xid'],position=(px,py),server_generation=ready['server_generation'],target_generation=ready['target_generation'])
            else:
                move_pointer(px,py,ready['server_generation'],target=window['xid'],target_generation=ready['target_generation'])
        return {'effect':'dispatched','verification':'Popup input sent; observe the menu or resulting application state.'}
