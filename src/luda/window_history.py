"""Bounded, observational maximize references; never restores a saved rectangle."""
from collections import OrderedDict
import hashlib

SCOPE='Historical same-generation geometry comparison; external changes between observations can go undetected.'


def geometry(window):
    return {'client_bounds':dict(window['bounds']),'frame_bounds':dict(window['frame_bounds'])}


def signature(window):
    return (geometry(window),window.get('workspace'))


def hints(properties):
    for index,line in enumerate(properties.splitlines()):
        if line.startswith('WM_NORMAL_HINTS'):
            return hashlib.sha256('\n'.join(properties.splitlines()[index:]).encode()).hexdigest()
    return None


def normal(properties):
    return not any(atom in properties for atom in ('_NET_WM_STATE_MAXIMIZED_VERT','_NET_WM_STATE_MAXIMIZED_HORZ','_NET_WM_STATE_HIDDEN','_NET_WM_STATE_FULLSCREEN'))


def maximized(properties):
    return all(atom in properties for atom in ('_NET_WM_STATE_MAXIMIZED_VERT','_NET_WM_STATE_MAXIMIZED_HORZ')) and not any(atom in properties for atom in ('_NET_WM_STATE_HIDDEN','_NET_WM_STATE_FULLSCREEN'))


class WindowHistory:
    def __init__(self):self.entries=OrderedDict()
    def clear(self):self.entries.clear()
    def put(self,window_id,record):
        self.entries.pop(window_id,None);self.entries[window_id]=record
        while len(self.entries)>64:self.entries.popitem(last=False)
    def observe(self,windows):
        current={w['window_id']:w for w in windows}
        for key,record in list(self.entries.items()):
            if key not in current:
                self.entries.pop(key,None)
            elif not record.get('reason') and signature(current[key])!=record['maximized_signature']:
                self.put(key,{'reason':'observed_geometry_changed'})
    def take(self,window_id):return self.entries.pop(window_id,None)
    def invalidate(self,window_id):
        if window_id in self.entries:self.put(window_id,{'reason':'another_window_action'})
    def context(self,window,properties,previous,stable=True):
        if not stable:return {'reason':'geometry_changed_during_read'}
        if hints(properties) is None:return {'reason':'size_hints_unavailable'}
        if previous and not previous.get('reason'):
            if maximized(properties) and signature(window)==previous['maximized_signature'] and hints(properties)==previous['hints']:
                return previous
            return {'reason':'state_geometry_or_hints_changed'}
        return previous or {'reason':'no_prior_maximize'}
    def capture(self,window_id,before,before_properties,after,after_properties,stable=True):
        if not stable or not normal(before_properties) or not maximized(after_properties) or hints(before_properties) is None or hints(before_properties)!=hints(after_properties):
            self.put(window_id,{'reason':'maximize_reference_unavailable'});return
        self.put(window_id,{'reference':geometry(before),'maximized_signature':signature(after),'hints':hints(after_properties)})
    def compare(self,record,after,after_properties):
        result={'status':'unknown','scope':SCOPE}
        if not record or record.get('reason'):
            result['reason']=(record or {}).get('reason','no_prior_maximize');return result
        if not normal(after_properties) or hints(after_properties)!=record['hints']:
            result['reason']='state_or_hints_changed_during_restore';return result
        result.update(status='matched' if geometry(after)==record['reference'] else 'nonmatching',prior_geometry=record['reference'])
        return result
