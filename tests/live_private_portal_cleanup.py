"""Real disconnected FUSE test in an ordinary caller's isolated user/mount namespace.

Requires Linux unshare, /dev/fuse and fusermount3 in PATH. No GUI or portal service.
"""
import ctypes
import errno
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from private_directory_cleanup import cleanup,mounts


def inside():
    library=ctypes.CDLL(None,use_errno=True)
    with tempfile.TemporaryDirectory(prefix='luda-owned-fuse-proof-') as parent:
        root=Path(parent)/'private';root.mkdir(mode=0o700);runtime=root/'runtime';runtime.mkdir(mode=0o700)
        endpoint=runtime/'doc';endpoint.mkdir(mode=0o700)
        other=Path(parent)/'unrelated';other.mkdir();(other/'marker').write_text('preserve')
        fd=os.open('/dev/fuse',os.O_RDWR)
        options=f'fd={fd},rootmode=40000,user_id={os.getuid()},group_id={os.getgid()}'.encode()
        result=library.mount(b'portal',os.fsencode(endpoint),b'fuse.portal',0,options)
        if result:
            error=ctypes.get_errno();os.close(fd);raise OSError(error,os.strerror(error))
        os.close(fd) # Real dead connection; no simulated rmtree exception.
        try:
            try:os.listdir(endpoint);raise AssertionError('Expected disconnected FUSE')
            except OSError as exc:assert exc.errno==errno.ENOTCONN,exc
            before=[entry for entry in mounts() if entry['path']==endpoint]
            assert len(before)==1 and before[0]['type']=='fuse.portal',before
            # Demonstrate the exact original failure without removing state first.
            try:shutil.rmtree(root);raise AssertionError('Expected original cleanup failure')
            except OSError as exc:assert exc.errno==errno.ENOTCONN,exc
            outcome=cleanup(root)
            assert outcome=={'status':'removed','owned_portal_mounts_detached':1}
            assert not root.exists() and not any(entry['path']==endpoint for entry in mounts())
            assert (other/'marker').read_text()=='preserve'
            print(json.dumps({'original':'rmtree ENOTCONN','fixed':outcome,'unrelated_preserved':True,'mount_absent':True,'namespace_uid':os.getuid()}))
        finally:
            # Only our exact mount, in a namespace destroyed when this process exits.
            library.umount2(os.fsencode(endpoint),2)

if __name__=='__main__':
    if '--inside' in sys.argv:inside()
    else:
        assert os.getuid()!=0,'Start as an ordinary user; namespace maps only that user.'
        print(json.dumps({'caller_uid':os.getuid(),'isolation':'new user and mount namespaces'}),flush=True)
        raise SystemExit(subprocess.call(['unshare','--user','--map-root-user','--mount',sys.executable,__file__,'--inside']))
