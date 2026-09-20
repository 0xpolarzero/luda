"""Fresh-tree predicates and explicitly scoped sampled-pixel stability."""
import base64
import hashlib
import io
import math
import time

from PIL import Image
from .common import DesktopError, _current_operation, checkpoint, operation_scope
from .timing import elapsed_time


class ConditionWaitsMixin:
    def wait_condition(self, condition, window_id=None, element_id=None, text=None,
                       timeout=5, name=None, role=None, states=None, stable_for=.3):
        extended = {'element_present', 'element_absent', 'pixels_stable'}
        if condition not in extended:
            if any(v is not None for v in (name, role, states)) or stable_for != .3:
                raise DesktopError('INVALID_ARGUMENT', 'Filters and stable_for belong to the corresponding extended wait conditions.')
            return self.wait_for(condition, window_id=window_id, element_id=element_id, text=text, timeout=timeout)
        if isinstance(timeout, bool) or not isinstance(timeout, (int,float)) or not math.isfinite(timeout) or not 0 <= timeout <= 10:
            raise DesktopError('INVALID_ARGUMENT', 'timeout must be finite and within 0–10 seconds.')
        if not isinstance(window_id,str) or not window_id or element_id is not None or text is not None:
            raise DesktopError('INVALID_ARGUMENT', 'Extended conditions require window_id, without element_id or text.')
        if condition.startswith('element_'):
            if stable_for != .3:
                raise DesktopError('INVALID_ARGUMENT', 'stable_for applies only to pixels_stable.')
            if any(v is not None and (not isinstance(v,str) or not v.strip()) for v in (name,role)):
                raise DesktopError('INVALID_ARGUMENT', 'Name and role filters must be nonempty strings.')
            if states is not None and (not isinstance(states,list) or not states or any(not isinstance(s,str) or not s.strip() for s in states)):
                raise DesktopError('INVALID_ARGUMENT', 'States must be a nonempty list of nonempty state names.')
            if name is None and role is None and states is None:
                raise DesktopError('INVALID_ARGUMENT', 'Element waits require a meaningful name, role or states filter.')
        else:
            if any(v is not None for v in (name,role,states)):
                raise DesktopError('INVALID_ARGUMENT', 'Pixel stability does not accept element filters.')
            if isinstance(stable_for,bool) or not isinstance(stable_for,(int,float)) or not math.isfinite(stable_for) or not .1 <= stable_for <= 10 or stable_for > timeout:
                raise DesktopError('INVALID_ARGUMENT', 'stable_for must be 0.1–10 seconds and no greater than timeout.')
        parent = _current_operation.get()
        budget = max(timeout,.001)
        if parent:
            budget = min(budget,max(0,parent.deadline-elapsed_time()))
        # Preserve the caller's cancellation and human-pause guard while capping
        # slow observation helpers to this wait's own deadline.
        own_deadline=elapsed_time()+timeout
        try:
            with operation_scope(timeout=budget, cancelled=parent.cancelled if parent else None,
                                 guard=parent.guard if parent else None):
                return self._wait_observation(condition,window_id,timeout,name,role,states,stable_for)
        except DesktopError as exc:
            if exc.code=='TIMEOUT' and elapsed_time()>=own_deadline and (parent is None or parent.deadline>own_deadline):
                return {'effect':'none','condition':condition,'matched':False,'reason':'condition_timeout'}
            raise

    def _wait_observation(self,condition,window_id,timeout,name,role,states,stable_for):
        deadline=elapsed_time()+timeout
        polls=0
        previous=None
        stable_since=None
        while True:
            checkpoint()
            polls+=1
            if condition.startswith('element_'):
                tree=self.inspect(window_id,limit=500,name=name,role=role,states=states,max_depth=60)
                nodes=tree.get('nodes',[])
                complete=(tree.get('available') is True and tree.get('truncated') is False
                          and not tree.get('unreadable_nodes') and not tree.get('unreadable_branches')
                          and not any(tree.get('truncation',{}).values()))
                if condition=='element_absent' and not complete:
                    raise DesktopError('VERIFICATION_LIMIT','Cannot prove absence from an unavailable, truncated or partially unreadable accessibility tree.')
                matched=bool(nodes) and tree.get('available') is True if condition=='element_present' else not nodes
                if matched:
                    return {'effect':'verified','condition':condition,'matched':True,'polls':polls,
                            'window_id':window_id,'elements':nodes,'coverage_complete':complete,
                            'verification':'Fresh accessibility tree matches requested name/role substrings and required states.'}
            else:
                try:
                    sample=self._pixel_sample(window_id)
                except DesktopError as exc:
                    if exc.code not in ('DESKTOP_CHANGED','STALE_OBSERVATION'):
                        raise
                    sample=None
                now=elapsed_time()
                if sample is None:
                    previous,stable_since=None,None
                elif sample!=previous:
                    previous,stable_since=sample,now
                elif now-stable_since>=stable_for:
                    return {'effect':'verified','condition':condition,'matched':True,'polls':polls,
                            'window_id':window_id,'stable_seconds':now-stable_since,
                            'verification':'Sampled returned-screenshot pixels in the target client rectangle were identical. This is not application idleness.'}
            remaining=deadline-elapsed_time()
            if remaining<=0:
                return {'effect':'none','condition':condition,'matched':False,'polls':polls,'reason':'condition_timeout'}
            time.sleep(min(.05,remaining))

    def _pixel_sample(self,window_id):
        shot=self.observe(max_width=2560)
        window=next((w for w in shot['windows'] if w['window_id']==window_id),None)
        if window is None:
            raise DesktopError('STALE_TARGET','Target window is no longer present.')
        b=window['bounds'];size=shot['desktop_size'];image_size=shot['image_size']
        if b['width']<=0 or b['height']<=0 or b['x']<0 or b['y']<0 or b['x']+b['width']>size['width'] or b['y']+b['height']>size['height']:
            raise DesktopError('OUT_OF_BOUNDS','Pixel stability currently requires the full target client rectangle inside the desktop image.')
        sx=image_size['width']/size['width'];sy=image_size['height']/size['height']
        rectangle=(math.floor(b['x']*sx),math.floor(b['y']*sy),math.ceil((b['x']+b['width'])*sx),math.ceil((b['y']+b['height'])*sy))
        with Image.open(io.BytesIO(base64.b64decode(shot['image_base64'],validate=True))) as image:
            crop=image.convert('RGB').crop(rectangle)
            digest=hashlib.sha256(crop.tobytes()).hexdigest()
        # Layout/focus changes cannot be hidden by matching pixel colors.
        return (digest,rectangle,window['active'],window.get('workspace'),tuple(size.values()))
