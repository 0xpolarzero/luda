"""Window-manager and pointer operations; caller holds Desktop.transaction()."""
import math
import time
import uuid
from .common import DesktopError, process_identity, run
from .timing import elapsed_time


def integer(value, name, low, high):
    if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
        raise DesktopError('INVALID_ARGUMENT', f'{name} must be an integer from {low} to {high}.')
    return value


def properties(xid):
    return run(['xprop', '-id', str(xid), '_NET_WM_STATE']).decode(errors='replace')


class InteractionMixin:
    """Public operations use existing opaque window/screenshot identities."""
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
        run(['wmctrl', '-s', str(workspace)], effect='uncertain')
        return self._await_state(lambda: any(w['workspace'] == workspace and w['active'] for w in self.workspaces()),
                                 {'workspace': workspace})

    def _await_state(self, predicate, extra):
        deadline = time.monotonic() + 1.5
        while True:
            if predicate():
                return {'effect': 'verified', 'verification': 'Window-manager state matches request.', **extra}
            if time.monotonic() >= deadline:
                return {'effect': 'dispatched', 'verification': 'Requested state was not observed; inspect before retrying.', **extra}
            time.sleep(.04)

    def manage_window(self, window_id, action, x=None, y=None, width=None, height=None, workspace=None):
        actions = {'move', 'resize', 'maximize', 'minimize', 'restore', 'close', 'workspace'}
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
        if action == 'move': command = ['wmctrl','-ir',xid,'-e',f'0,{x},{y},-1,-1']
        elif action == 'resize': command = ['xdotool','windowsize',xid,str(width),str(height)]
        elif action == 'minimize': command = ['xdotool','windowminimize',xid]
        elif action == 'close': command = ['wmctrl','-ic',xid]
        elif action == 'workspace': command = ['wmctrl','-ir',xid,'-t',str(workspace)]
        else: command = ['wmctrl','-ir',xid,'-b',('add' if action == 'maximize' else 'remove')+',maximized_vert,maximized_horz']
        run(command, effect='uncertain')
        if action == 'restore':
            run(['xdotool','windowmap',xid], effect='uncertain')
        def matches():
            current = next((v for v in self.list_windows() if v['window_id'] == window_id), None)
            if action == 'close': return current is None
            if current is None: return False
            if action == 'move': return all(current['frame_bounds'][key] == value for key,value in [('x',x),('y',y)])
            if action == 'resize': return current['bounds']['width'] == width and current['bounds']['height'] == height
            if action == 'workspace': return current['workspace'] == workspace
            state = properties(current['xid'])
            if action == 'minimize': return '_NET_WM_STATE_HIDDEN' in state
            maximized = all('_NET_WM_STATE_MAXIMIZED_'+part in state for part in ('VERT','HORZ'))
            if action == 'maximize': return maximized
            return not any(token in state for token in ('_NET_WM_STATE_HIDDEN','_NET_WM_STATE_MAXIMIZED_VERT','_NET_WM_STATE_MAXIMIZED_HORZ'))
        return self._await_state(matches, {'window_id':window_id,'action':action})

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
        iw,ih = snap['image']; nw,nh = snap['native']
        if not 0 <= x < iw or not 0 <= y < ih:
            raise DesktopError('OUT_OF_BOUNDS', 'Point is outside screenshot.')
        px,py = int(x*nw/iw),int(y*nh/ih)
        # An owned menu is part of its window's interaction surface. Agents use
        # the same image coordinates and owner window ID for menus and clients.
        for popup in reversed(snap.get('popups',[])):
            b = popup['bounds']
            if popup['owner_window_id']==window_id and b['x']<=px<b['x']+b['width'] and b['y']<=py<b['y']+b['height']:
                return self._popup_point(window_id,popup['popup_id'],snapshot_id,x,y)
        if self.display().surface_at(px,py)!=self.display().root_surface(w['xid']):
            raise DesktopError('OCCLUDED_TARGET','Another surface covers this point; observe again.')
        b = w['bounds']
        if not b['x'] <= px < b['x']+b['width'] or not b['y'] <= py < b['y']+b['height']:
            raise DesktopError('OUT_OF_BOUNDS', 'Point is outside target client bounds.')
        return px,py

    def hover(self, window_id, snapshot_id, x, y):
        px,py = self._interaction_point(window_id,snapshot_id,x,y)
        run(['xdotool','mousemove',str(px),str(py)], effect='uncertain')
        return {'effect':'dispatched','verification':'Pointer motion sent; observe tooltips or hover state.'}

    def drag_between(self, source_window_id, target_window_id, snapshot_id, x, y, end_x, end_y, button='left'):
        buttons = {'left':'1','middle':'2','right':'3'}
        if button not in buttons: raise DesktopError('INVALID_ARGUMENT','Unknown mouse button.')
        start = self._interaction_point(source_window_id,snapshot_id,x,y)
        end = self._interaction_point(target_window_id,snapshot_id,end_x,end_y,False)
        run(['xdotool','mousemove',str(start[0]),str(start[1])],effect='uncertain')
        failure = None
        try:
            run(['xdotool','mousedown',buttons[button]],effect='uncertain')
            for step in range(1,16):
                p = [round(start[i]+(end[i]-start[i])*step/15) for i in (0,1)]
                run(['xdotool','mousemove',str(p[0]),str(p[1])],effect='uncertain')
                time.sleep(.02)
        except BaseException as exc:
            failure = exc
            raise
        finally:
            try:
                run(['xdotool','mouseup',buttons[button]],effect='uncertain',cleanup=True)
            except DesktopError as cleanup_error:
                if failure is None:
                    raise
                if isinstance(failure, DesktopError):
                    failure.details['button_release_failed'] = cleanup_error.code
                    failure.effect = 'uncertain'
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

    def _popup_point(self, owner_window_id, popup_id, snapshot_id, x, y):
        if any(isinstance(v,bool) or not isinstance(v,(int,float)) or not math.isfinite(v) for v in (x,y)):
            raise DesktopError('INVALID_ARGUMENT','Coordinates must be finite numbers.')
        snap=self.snapshots.get(snapshot_id)
        if not snap or elapsed_time()-snap['time']>=15:
            raise DesktopError('STALE_OBSERVATION','Screenshot expired; observe again.')
        observed=next((p for p in snap.get('popups',[]) if p['popup_id']==popup_id and p['owner_window_id']==owner_window_id),None)
        if observed is None:raise DesktopError('STALE_TARGET','Popup is not authorized by this screenshot and owner.')
        self.target_window(owner_window_id)
        if self.signature(list(self.windows.values()))!=snap['signature']:
            raise DesktopError('STALE_OBSERVATION','Window layout or focus changed; observe again.')
        current=self.observe_popups(list(self.windows.values()))
        if self.popup_signature(current)!=self.popup_signature(snap['popups']):
            raise DesktopError('STALE_OBSERVATION','Popup layout or ownership changed; observe again.')
        root=self.display().geometry(self.display().root)
        if (root['width'],root['height'])!=tuple(snap['native']):
            raise DesktopError('STALE_OBSERVATION','Display resolution changed; observe again.')
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
        px,py=self._popup_point(owner_window_id,popup_id,snapshot_id,x,y)
        run(['xdotool','mousemove',str(px),str(py)],effect='uncertain')
        if kind!='hover':
            run(['xdotool','click','--repeat',str(count),'--delay','100',buttons[button] if kind=='click' else directions[direction]],effect='uncertain')
        return {'effect':'dispatched','verification':'Popup input sent; observe the menu or resulting application state.'}
