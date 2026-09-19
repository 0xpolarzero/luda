"""System-Python/GI bridge; no shell interpretation and no inherited app pipes."""
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import unquote,urlsplit


class AppError(Exception):
    def __init__(self,code,message):super().__init__(message);self.code=code


def uri_for(value):
    if value.startswith('/'):
        path=Path(value)
        if not path.exists():raise AppError('FILE_NOT_FOUND','A requested local path does not exist.')
        return path.as_uri(),True
    if any(c.isspace() for c in value) or re.search(r'%(?![0-9A-Fa-f]{2})',value):
        raise AppError('INVALID_ARGUMENT','URIs must encode whitespace and use valid percent escapes.')
    parsed=urlsplit(value)
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9+.-]*',parsed.scheme):
        raise AppError('INVALID_ARGUMENT','Use an absolute existing path or URI with an explicit scheme.')
    if parsed.scheme in {'http','https'} and not parsed.netloc:
        raise AppError('INVALID_ARGUMENT','HTTP and HTTPS URIs require a host.')
    if parsed.scheme=='file':
        if parsed.netloc not in {'','localhost'} or not parsed.path.startswith('/'):
            raise AppError('INVALID_ARGUMENT','File URIs must refer to an absolute local path.')
        path=Path(unquote(parsed.path))
        if not path.exists():raise AppError('FILE_NOT_FOUND','A requested local file URI does not exist.')
        return value,True
    return value,False


def main():
    effect='none'
    try:
        import gi
        gi.require_version('Gio','2.0')
        from gi.repository import Gio,GLib
        request=json.loads(sys.stdin.buffer.read(100000))
        if request['method']=='list':
            needle=request['query'].casefold();found=[]
            for app in Gio.AppInfo.get_all():
                identity=app.get_id()
                if not identity or not identity.endswith('.desktop') or not app.should_show():continue
                if not app.get_executable() and not (isinstance(app,Gio.DesktopAppInfo) and app.get_boolean('DBusActivatable')):continue
                name=app.get_display_name() or app.get_name() or identity
                description=app.get_description() or ''
                if needle not in (' '.join((identity,name,description))).casefold():continue
                found.append({'application_id':identity,'name':name,'description':description,
                              'supports_files':bool(app.supports_files()),'supports_uris':bool(app.supports_uris())})
            found.sort(key=lambda item:(item['name'].casefold(),item['application_id']))
            result={'applications':found[:request['limit']],'total_matches':len(found),'truncated':len(found)>request['limit']}
        elif request['method']=='launch':
            try:app=Gio.DesktopAppInfo.new(request['application_id'])
            except (TypeError,GLib.Error):app=None
            if app is None or (not app.get_executable() and not app.get_boolean('DBusActivatable')):raise AppError('APPLICATION_NOT_FOUND','Desktop entry is missing or invalid; list installed applications again.')
            inputs=[uri_for(value) for value in request['files_or_uris']]
            if inputs and not app.supports_files() and not app.supports_uris():
                raise AppError('UNSUPPORTED_INPUT','This desktop entry does not accept files or URIs.')
            if any(not local for _,local in inputs) and not app.supports_uris():
                raise AppError('UNSUPPORTED_INPUT','This desktop entry accepts local files, not remote URIs.')
            context=Gio.AppLaunchContext()
            context.setenv('ACCESSIBILITY_ENABLED','1')
            context.setenv('QT_LINUX_ACCESSIBILITY_ALWAYS_ON','1')
            context.unsetenv('NO_AT_BRIDGE')
            pids=[]
            completion={'done':False,'failed':False};loop=GLib.MainLoop()
            def launched(*unused):completion['done']=True;loop.quit()
            def launch_failed(*unused):completion['failed']=True;loop.quit()
            context.connect('launched',launched);context.connect('launch-failed',launch_failed)
            def pid_callback(info,pid,*unused):pids.append(pid)
            def child_setup(*unused):os.setsid()
            # Every launched process receives /dev/null; no inherited MCP pipes.
            # A new session also isolates newly spawned apps from helper cleanup.
            with open(os.devnull,'r+b',buffering=0) as sink:
                effect='uncertain'
                accepted=app.launch_uris_as_manager_with_fds([uri for uri,_ in inputs],context,
                    GLib.SpawnFlags.SEARCH_PATH|GLib.SpawnFlags.DO_NOT_REAP_CHILD,
                    child_setup,None,pid_callback,None,sink.fileno(),sink.fileno(),sink.fileno())
            if not accepted:raise AppError('LAUNCH_FAILED','Desktop service did not accept the launch request.')
            if not completion['done'] and not completion['failed']:
                def expired():
                    loop.quit()
                    return False
                timer=GLib.timeout_add(4000,expired)
                try:loop.run()
                finally:
                    if GLib.MainContext.default().find_source_by_id(timer):GLib.source_remove(timer)
            if not completion['done'] or completion['failed']:
                raise AppError('LAUNCH_FAILED','Application activation did not complete; inspect before retrying.')
            result={'effect':'dispatched','application_id':request['application_id'],'spawned_pids':pids,
                    'verification':'Launch accepted; observe windows to confirm readiness. An existing singleton may handle the request.'}
        else:raise AppError('INVALID_ARGUMENT','Unknown application operation.')
        print(json.dumps({'result':result}))
    except AppError as exc:print(json.dumps({'error':{'code':exc.code,'message':str(exc),'effect':effect}}))
    except ImportError:print(json.dumps({'error':{'code':'DEPENDENCY_MISSING','message':'System Python requires PyGObject and Gio.','effect':'none'}}))
    except (ValueError,KeyError,TypeError):print(json.dumps({'error':{'code':'INVALID_ARGUMENT','message':'Malformed application request or URI.','effect':effect}}))
    except Exception:
        # GIO may include user URIs in its exception; do not expose those in logs.
        print(json.dumps({'error':{'code':'LAUNCH_FAILED','message':'The desktop application service rejected the operation.','effect':effect}}))


if __name__=='__main__':main()
