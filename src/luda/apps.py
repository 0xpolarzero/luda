"""Installed-application discovery and launch through native desktop entries."""
import json
import math
import time
from pathlib import Path
from .common import DesktopError, run, checkpoint, mark_effect


def _text(value, name, maximum):
    if not isinstance(value,str) or any(ord(c)<32 or ord(c)==127 for c in value):
        raise DesktopError('INVALID_ARGUMENT',f'{name} must be text without control characters.')
    try: size=len(value.encode('utf-8'))
    except UnicodeEncodeError as exc:raise DesktopError('INVALID_ARGUMENT',f'{name} contains an invalid Unicode surrogate.') from exc
    if size>maximum:raise DesktopError('INVALID_ARGUMENT',f'{name} exceeds {maximum} UTF-8 bytes.')
    return value


def _call(method, arguments):
    try:
        raw=run(['/usr/bin/python3',str(Path(__file__).with_name('_app_helper.py'))],
                data=json.dumps({'method':method,**arguments},ensure_ascii=False).encode(),timeout=5,
                effect='uncertain' if method=='launch' else 'none')
    except DesktopError as exc:
        if exc.code=='BACKEND_ERROR':
            raise DesktopError('LAUNCH_FAILED' if method=='launch' else 'BACKEND_ERROR',
                               'Application helper exited unexpectedly.',effect=exc.effect) from exc
        raise
    try:
        result=json.loads(raw)
        if not isinstance(result,dict):raise ValueError()
        if 'error' in result:
            error=result['error']
            raise DesktopError(error['code'],error['message'],effect=error.get('effect','none'))
        return result['result']
    except (ValueError,KeyError,TypeError) as exc:
        raise DesktopError('BACKEND_ERROR','Application helper returned an invalid response.') from exc


def list_applications(query='',limit=50):
    _text(query,'query',512)
    if isinstance(limit,bool) or not isinstance(limit,int) or not 1<=limit<=200:
        raise DesktopError('INVALID_ARGUMENT','limit must be an integer from 1 to 200.')
    return _call('list',{'query':query,'limit':limit})


def launch_application(application_id,files_or_uris=None):
    _text(application_id,'application_id',512)
    if not application_id.endswith('.desktop') or application_id.startswith('.') or '/' in application_id or '\\' in application_id:
        raise DesktopError('INVALID_ARGUMENT','Use an installed application_id ending in .desktop, not a command or path.')
    if files_or_uris is None:files_or_uris=[]
    if not isinstance(files_or_uris,list) or len(files_or_uris)>128:
        raise DesktopError('INVALID_ARGUMENT','files_or_uris must contain at most 128 paths or URIs.')
    for value in files_or_uris:
        _text(value,'file or URI',8192)
        if not value:raise DesktopError('INVALID_ARGUMENT','Files and URIs must not be empty.')
    if sum(len(v.encode('utf-8')) for v in files_or_uris)>65536:
        raise DesktopError('INVALID_ARGUMENT','Combined files and URIs exceed 64 KB.')
    return _call('launch',{'application_id':application_id,'files_or_uris':files_or_uris})


def launch_and_observe(desktop,application_id,files_or_uris=None,wait_timeout=1.0):
    """One launch followed by bounded observations, never document-readiness guesses."""
    if type(wait_timeout) not in (int,float) or not math.isfinite(wait_timeout) or not 0<=wait_timeout<=3:
        raise DesktopError('INVALID_ARGUMENT','wait_timeout must be a finite number from 0 to 3 seconds.')
    result=launch_application(application_id,files_or_uris)
    mark_effect('dispatched')
    observation={'state':'not_requested','candidates':[], 'total_candidates':0,'truncated':False,
                 'scope':'Windows match captured launch-process generations only; request-document readiness is not verified.'}
    result['window_observation']=observation
    if wait_timeout==0:return result
    identities=set()
    for item in result.get('spawned_processes',[]):
        if isinstance(item,dict) and type(item.get('pid')) is int and item['pid']>0 and isinstance(item.get('start'),str) and item['start'].isdigit():
            identities.add((item['pid'],item['start']))
    if not identities:
        observation['state']='unassociated'
        return result
    deadline=time.monotonic()+wait_timeout
    while True:
        checkpoint()
        try:
            windows=desktop.list_windows()
        except DesktopError as exc:
            if exc.code in ('CANCELLED','TIMEOUT'):raise
            checkpoint()
            observation.update(state='unavailable',reason='Window enumeration failed after launch.')
            return result
        checkpoint()
        candidates=[{k:w[k] for k in ('window_id','pid','start','title','active') if k in w}
                    for w in windows if (w.get('pid'),w.get('start')) in identities]
        unavailable=getattr(desktop,'window_diagnostics',{}).get('unavailable_count',0)
        count=len(candidates)
        observation.update(candidates=candidates[:50],total_candidates=count,truncated=count>50,
                           state='unavailable' if unavailable else 'multiple_candidates' if count>1 else 'one_candidate' if count==1 else 'pending')
        if unavailable:observation['unavailable_windows']=unavailable
        else:observation.pop('unavailable_windows',None)
        remaining=deadline-time.monotonic()
        if remaining<=0:return result
        time.sleep(min(.05,remaining))
