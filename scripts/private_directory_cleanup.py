"""Remove owned test state only after detached private document-portal mounts."""
import contextlib
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile


def unescape(value):
    return re.sub(r'\\([0-7]{3})',lambda match:chr(int(match[1],8)),value)


def mounts():
    result=[]
    for line in Path('/proc/self/mountinfo').read_text().splitlines():
        fields=line.split();separator=fields.index('-')
        result.append({'id':fields[0],'path':Path(unescape(fields[4])),
                       'type':fields[separator+1],'options':fields[separator+3].split(',')})
    return result


def cleanup(directory):
    base=Path(directory).absolute()
    # Do not resolve through a broken FUSE endpoint or a symlink.
    info=base.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o700:
        raise RuntimeError('Private test directory ownership or mode changed; retained for review.')
    inside=lambda entry:entry['path']==base or base in entry['path'].parents
    found=[entry for entry in mounts() if inside(entry)]
    expected=base/'runtime'/'doc'
    if found:
        runtime=(base/'runtime').lstat()
        if not stat.S_ISDIR(runtime.st_mode) or runtime.st_uid!=os.getuid() or stat.S_IMODE(runtime.st_mode)!=0o700:
            raise RuntimeError('Private runtime ownership or mode changed; retained for review.')
        if len(found)!=1 or found[0]['path']!=expected or found[0]['type']!='fuse.portal' or f'user_id={os.getuid()}' not in found[0]['options']:
            raise RuntimeError('Unexpected mount in private test directory; retained for review.')
        utility=shutil.which('fusermount3') or shutil.which('fusermount')
        if utility is None:raise RuntimeError('Private portal cleanup requires fusermount3; retained for review.')
        # Bind to the same mount-table record immediately before unmount.
        if [entry for entry in mounts() if inside(entry)]!=found:
            raise RuntimeError('Private portal mount changed before cleanup; retained for review.')
        completed=subprocess.run([utility,'-u','-z','--',str(expected)],stdin=subprocess.DEVNULL,
                                 stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=3)
        remaining=[entry for entry in mounts() if inside(entry)]
        # A terminating portal may detach itself between our identity check and
        # fusermount. Confirm the desired state even when the utility lost that race.
        if remaining:
            raise RuntimeError(f'Private portal detach was not confirmed (unmount_exit={completed.returncode}, remaining_mounts={len(remaining)}); retained for review.')
    shutil.rmtree(base)
    result={'status':'removed','owned_portal_mounts_detached':len(found)}
    if found and completed.returncode:
        result['unmount_exit']=completed.returncode
        result['mount_absence_confirmed']=True
    return result


@contextlib.contextmanager
def private_directory(report, *, prefix='luda-matrix-'):
    directory=tempfile.mkdtemp(prefix=prefix)
    try:
        yield directory
    finally:
        # Keep the fixture verdict even if cleanup separately fails.
        if 'status' in report:report['fixture_status']='passed' if report.get('returncode')==0 else report['status']
        try:report['private_directory_cleanup']=cleanup(directory)
        except Exception as exc:
            report['private_directory_cleanup']={'status':'unconfirmed','directory_retained':True,'directory':directory,'reason':str(exc)}
            raise
