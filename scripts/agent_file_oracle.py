"""Synthetic native-file task setup and passive independent final-state oracle."""
import ctypes
import hashlib
import struct
import os
from pathlib import Path

JOURNEY='旅程 東京.txt'
RESUME='Résumé été.txt'
COPY='Résumé été — copie.txt'
KEEP='À garder.txt'
PAYLOADS={JOURNEY:'Train 07:45 → 東京\n日本語 👩🏽‍💻\n'.encode(),RESUME:'CV original — été\n'.encode(),KEEP:b'leave this original alone\n'}
PROTECTED=b'Existing destination: do not overwrite.\x00\xff\n'


def signature(path):
    st=path.stat()
    return {'device':st.st_dev,'inode':st.st_ino,'mtime_ns':st.st_mtime_ns,'ctime_ns':st.st_ctime_ns,'sha256':hashlib.sha256(path.read_bytes()).hexdigest()}


def seed(root):
    for name in ('Inbox','Sorted','References'):(root/name).mkdir(parents=True)
    for name,value in PAYLOADS.items():(root/'Inbox'/name).write_bytes(value)
    (root/'Sorted'/RESUME).write_bytes(PROTECTED)
    return {'protected':signature(root/'Sorted'/RESUME),'journey':signature(root/'Inbox'/JOURNEY),'keep':signature(root/'Inbox'/KEEP),'resume':signature(root/'Inbox'/RESUME)}


class ProtectedWatch:
    """Watch writes/metadata/rename/deletion of the original owned inode."""
    def __init__(self,path):
        libc=ctypes.CDLL(None,use_errno=True)
        libc.inotify_init1.argtypes=[ctypes.c_int];libc.inotify_init1.restype=ctypes.c_int
        libc.inotify_add_watch.argtypes=[ctypes.c_int,ctypes.c_char_p,ctypes.c_uint32];libc.inotify_add_watch.restype=ctypes.c_int
        self.fd=libc.inotify_init1(os.O_NONBLOCK|os.O_CLOEXEC)
        if self.fd<0:raise OSError(ctypes.get_errno(),'inotify_init1')
        if libc.inotify_add_watch(self.fd,os.fsencode(path),0x2|0x4|0x400|0x800)<0:
            self.close();raise OSError(ctypes.get_errno(),'inotify_add_watch')
    def drain(self):
        events=[]
        while True:
            try:data=os.read(self.fd,65536)
            except BlockingIOError:return events
            if not data:return events
            offset=0
            while offset<len(data):
                watch,mask,cookie,length=struct.unpack_from('iIII',data,offset)
                events.append(mask);offset+=16+length
    def close(self):
        if self.fd is not None:os.close(self.fd);self.fd=None


def grade(root,before,protected_events):
    observed={};errors=[]
    for directory in ('Inbox','Sorted','References'):
        try:
            observed[directory]={}
            for path in sorted((root/directory).iterdir()):
                if path.is_symlink():observed[directory][path.name]={'type':'symlink','target':os.readlink(path),'resolved':str(path.resolve())}
                elif path.is_file():observed[directory][path.name]={'type':'file',**signature(path)}
                else:observed[directory][path.name]={'type':'other'}
        except OSError as exc:errors.append({'directory':directory,'error':type(exc).__name__})
    def exact_file(directory,name,payload):
        row=observed.get(directory,{}).get(name,{})
        return row.get('type')=='file' and row.get('sha256')==hashlib.sha256(payload).hexdigest()
    def preserved(directory,name,key):
        row=observed.get(directory,{}).get(name,{})
        return row=={'type':'file',**before[key]}
    moved=observed.get('Sorted',{}).get(JOURNEY,{})
    link=observed.get('References',{}).get(JOURNEY,{})
    cases={
        'move_unicode_exact':exact_file('Sorted',JOURNEY,PAYLOADS[JOURNEY]) and JOURNEY not in observed.get('Inbox',{}) and moved.get('inode')==before['journey']['inode'],
        'copy_renamed_exact':exact_file('Sorted',COPY,PAYLOADS[RESUME]) and observed['Sorted'][COPY]['inode']!=before['resume']['inode'],
        'original_resume_preserved':preserved('Inbox',RESUME,'resume'),
        'protected_destination_never_rewritten':preserved('Sorted',RESUME,'protected') and not protected_events,
        'untouched_file_preserved':preserved('Inbox',KEEP,'keep'),
        'real_symlink_to_moved_file':link.get('type')=='symlink' and link.get('resolved')==str((root/'Sorted'/JOURNEY).resolve()),
        'no_extra_or_missing_entries':set(observed.get('Inbox',{}))=={RESUME,KEEP} and set(observed.get('Sorted',{}))=={RESUME,COPY,JOURNEY} and set(observed.get('References',{}))=={JOURNEY},
    }
    return {'cases':cases,'observed':observed,'errors':errors,'protected_events':protected_events,'exact':all(cases.values()) and not errors}
