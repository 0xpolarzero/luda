"""Installed-application discovery and launch through native desktop entries."""
import json
from pathlib import Path
from .common import DesktopError, run


def _text(value, name, maximum):
    if not isinstance(value,str) or any(ord(c)<32 or ord(c)==127 for c in value):
        raise DesktopError('INVALID_ARGUMENT',f'{name} must be text without control characters.')
    try: size=len(value.encode('utf-8'))
    except UnicodeEncodeError as exc:raise DesktopError('INVALID_ARGUMENT',f'{name} contains an invalid Unicode surrogate.') from exc
    if size>maximum:raise DesktopError('INVALID_ARGUMENT',f'{name} exceeds {maximum} UTF-8 bytes.')
    return value


def _call(method, arguments):
    raw=run(['/usr/bin/python3',str(Path(__file__).with_name('_app_helper.py'))],
            data=json.dumps({'method':method,**arguments}).encode(),timeout=5,
            effect='uncertain' if method=='launch' else 'none')
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
