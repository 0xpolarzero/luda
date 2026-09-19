"""Disposable Xvfb proves real timeout containment and display reconnection."""
import json
import os
import select
import signal
import subprocess
import time
from unittest.mock import patch
from luda.common import DesktopError
from luda.x11 import X11

readfd,writefd=os.pipe()
p=subprocess.Popen(['Xvfb','-displayfd',str(writefd),'-screen','0','640x480x24','-nolisten','tcp'],pass_fds=(writefd,),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
os.close(writefd)
try:
    assert select.select([readfd],[],[],5)[0],'Xvfb startup timed out'
    number=os.read(readfd,32).decode().strip();assert number.isdigit(),number
    os.close(readfd)
    with patch.dict(os.environ,{'DISPLAY':':'+number}):
        x=X11(); root=x.root
        assert x.geometry(root)['width']==640
        p.send_signal(signal.SIGSTOP)
        started=time.monotonic()
        try:
            x.geometry(root)
            raise AssertionError('stopped X server should time out')
        except DesktopError as exc:
            assert exc.code=='TIMEOUT',exc.code
            elapsed=time.monotonic()-started
            assert elapsed<3.5,elapsed
        finally:
            p.send_signal(signal.SIGCONT)
        assert x.geometry(root)['width']==640
        p.terminate();p.wait(timeout=5)
        try:
            x.geometry(root)
            raise AssertionError('dead display should report unavailable')
        except DesktopError as exc:
            assert exc.code=='DISPLAY_UNAVAILABLE',exc.code
        p=subprocess.Popen(['Xvfb',':'+number,'-screen','0','800x600x24','-nolisten','tcp'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        deadline=time.monotonic()+5
        while True:
            try:
                geometry=x.geometry(x.root)
                if geometry['width']==800:break
            except DesktopError:pass
            if time.monotonic()>deadline:raise AssertionError('display restart failed')
            time.sleep(.05)
        x.close()
        assert x.geometry(x.root)['height']==600
        print(json.dumps({'stopped_server_timeout_seconds':round(elapsed,3),'restarted_geometry':geometry,'same_wrapper_reconnected':True}))
finally:
    if p.poll() is None:
        p.send_signal(signal.SIGCONT);p.terminate();p.wait(timeout=5)
