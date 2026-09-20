"""A disposable companion releases a held input if its controlling process dies."""
from contextlib import contextmanager
import os
import selectors
import subprocess
import sys
from .common import DesktopError, run, stop_process


@contextmanager
def held_button(button):
    if button not in ('1','2','3'):
        raise DesktopError('INVALID_ARGUMENT','Unsupported held mouse button.')
    reader,writer=os.pipe()
    child=None
    try:
        child=subprocess.Popen([sys.executable,'-m','luda._input_guard',str(reader),button],
                               pass_fds=(reader,),stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,
                               stderr=subprocess.DEVNULL,start_new_session=True)
        os.close(reader);reader=None
        with selectors.DefaultSelector() as ready:
            ready.register(child.stdout,selectors.EVENT_READ)
            if not ready.select(1) or child.stdout.read(1)!=b'R':
                raise DesktopError('INPUT_GUARD_UNAVAILABLE','Input cleanup companion did not become ready; no button pressed.')
        child.stdout.close()
        failure=None
        try:
            os.write(writer,b'A')
            run(['xdotool','mousedown',button],effect='uncertain')
            yield
        except BaseException as exc:
            failure=exc
            raise
        finally:
            try:
                run(['xdotool','mouseup',button],effect='uncertain',cleanup=True)
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
