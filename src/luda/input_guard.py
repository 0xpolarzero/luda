"""A disposable companion releases a held input if its controlling process dies."""
from contextlib import contextmanager
import os
import json
import selectors
import subprocess
import sys
from .common import DesktopError, run, stop_process, subprocess_environment


def _native_input(operation,button=None,generation=None,cleanup=False):
    request={'operation':operation,'button':button,'server_generation':generation}
    result=json.loads(run([sys.executable,'-m','luda._input_native'],data=json.dumps(request).encode()+b'\n',
                         timeout=2,cleanup=cleanup,effect='none' if operation=='generation' else 'uncertain',max_output_bytes=4096))
    if result.get('code'):raise DesktopError(result['code'],result['message'],effect=result.get('effect','none'))
    return result


@contextmanager
def held_button(button):
    if button not in ('1','2','3'):
        raise DesktopError('INVALID_ARGUMENT','Unsupported held mouse button.')
    generation=_native_input('generation')['server_generation']
    reader,writer=os.pipe()
    child=None
    try:
        child=subprocess.Popen([sys.executable,'-m','luda._input_guard',str(reader),button,generation],
                               pass_fds=(reader,),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL,start_new_session=True,env=subprocess_environment())
        os.close(reader);reader=None
        with selectors.DefaultSelector() as ready:
            ready.register(child.stdout,selectors.EVENT_READ)
            if not ready.select(1) or child.stdout.read(1)!=b'R':
                raise DesktopError('INPUT_GUARD_UNAVAILABLE','Input cleanup companion did not become ready; no button pressed.')
        child.stdout.close()
        failure=None
        try:
            os.write(writer,b'A')
            _native_input('press',button,generation)
            yield
        except BaseException as exc:
            failure=exc
            raise
        finally:
            try:
                result=_native_input('release',button,generation,cleanup=True)
                if not result.get('released') and not result.get('session_changed'):
                    raise DesktopError('INPUT_RELEASE_UNVERIFIED','Owned pointer button release was not verified.',effect='uncertain')
                if result.get('session_changed'):
                    if isinstance(failure,DesktopError):failure.details.update(session_changed=True,cleanup_skipped=True)
                    elif failure is None:raise DesktopError('SESSION_CHANGED','X server changed; cleanup input was skipped on the replacement session.',effect='uncertain',details={'cleanup_skipped':True})
            except DesktopError as exc:
                if isinstance(failure,DesktopError):
                    failure.details['button_release_failed']=exc.code
                    failure.effect='uncertain'
                if failure is None:raise
            else:
                # Disarm only after release succeeds. EOF otherwise asks the
                # companion to make its own bounded cleanup attempt.
                try:os.write(writer,b'D')
                except BrokenPipeError:pass
    finally:
        if reader is not None:os.close(reader)
        os.close(writer)
        if child:
            if child.stdout and not child.stdout.closed:child.stdout.close()
            try:child.wait(timeout=4)
            except subprocess.TimeoutExpired:stop_process(child)
