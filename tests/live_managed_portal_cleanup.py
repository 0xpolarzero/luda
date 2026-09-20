"""Actual managed-runner cleanup; only its GUI child is a test double.

Ordinary caller, private user/mount namespace, real dead fuse.portal endpoint.
No installed release, GUI, permission policy or shared mount changes.
"""
import ctypes,errno,importlib.util,json,os,subprocess,sys,tempfile
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
ROOT=Path(__file__).resolve().parents[1]

def inside():
 spec=importlib.util.spec_from_file_location('managed_runner',ROOT/'tests/evidence/managed-browser/run.py')
 runner=importlib.util.module_from_spec(spec);spec.loader.exec_module(runner)
 library=ctypes.CDLL(None,use_errno=True);seen=[];real_popen=subprocess.Popen
 with tempfile.TemporaryDirectory(prefix='managed-portal-proof-') as directory:
  parent=Path(directory);output=parent/'evidence';marker=parent/'unrelated';marker.write_text('preserve')
  class Child:
   pid=123456789
   def wait(self,timeout):return 0
  def launch(command,**kwargs):
   if command[0]!='xvfb-run':return real_popen(command,**kwargs)
   base=Path(kwargs['cwd']);endpoint=Path(kwargs['env']['XDG_RUNTIME_DIR'])/'doc';endpoint.mkdir(mode=0o700);seen.append((base,endpoint))
   fd=os.open('/dev/fuse',os.O_RDWR)
   options=f'fd={fd},rootmode=40000,user_id={os.getuid()},group_id={os.getgid()}'.encode()
   result=library.mount(b'portal',os.fsencode(endpoint),b'fuse.portal',0,options)
   error=ctypes.get_errno();os.close(fd)
   if result:raise OSError(error,os.strerror(error))
   try:os.listdir(endpoint);raise AssertionError('Expected actual disconnected mount')
   except OSError as exc:assert exc.errno==errno.ENOTCONN,exc
   return Child()
  try:
   # Namespace maps only the ordinary caller to UID0 for the raw mount.
   # Override this runner's GUI-account guard only: its GUI child is mocked;
   # cleanup still reads real UID0 and validates the actual owned mount.
   runner_os=SimpleNamespace(environ=os.environ,getuid=lambda:1001,killpg=lambda *_:None)
   with patch.object(runner.subprocess,'Popen',side_effect=launch),patch.object(runner,'os',runner_os):
    assert runner.main(['--repo',str(ROOT),'--output',str(output),'--prefix',str(parent/'unused-prefix')])==0
   proof=json.loads((output/'private-directory-cleanup.json').read_text())
   assert proof['fixture_status']=='passed' and proof['private_directory_cleanup']=={'status':'removed','owned_portal_mounts_detached':1},proof
   from private_directory_cleanup import mounts
   assert len(seen)==1 and not seen[0][0].exists() and all(row['path']!=seen[0][1] for row in mounts())
   assert marker.read_text()=='preserve'
   print(json.dumps({'uid':os.getuid(),'original_endpoint':'ENOTCONN','managed_wrapper':proof,'mount_absent':True,'unrelated_preserved':True}))
  finally:
   for _,endpoint in seen:library.umount2(os.fsencode(endpoint),2)

if __name__=='__main__':
 if '--inside' in sys.argv:inside()
 else:
  assert os.getuid()!=0,'Ordinary user required.'
  print(json.dumps({'caller_uid':os.getuid(),'isolation':'private user/mount namespace'}),flush=True)
  raise SystemExit(subprocess.call(['unshare','--user','--map-root-user','--mount',sys.executable,__file__,'--inside']))
