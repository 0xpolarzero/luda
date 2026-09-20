#!/usr/bin/env python3
"""Explicit root-only, pinned test packages in private mount/PID/network namespaces."""
import argparse,hashlib,json,os,pwd,grp,signal,subprocess,time
from pathlib import Path
from qualify import source_fingerprint
ROOT=Path(__file__).resolve().parents[1]
PACKAGES={
'pkexec_124-2ubuntu1.24.04.4_arm64.deb':'615857892e2e214385a74037eb22a4bda4448cdad30c6120dec32a3baa06bd89',
'gir1.2-polkit-1.0_124-2ubuntu1.24.04.4_arm64.deb':'53ea3e8e830c8ddc96de36a57395c6b84f7eef8bb4e14a647ce8ad42b507219c',
'polkitd_124-2ubuntu1.24.04.4_arm64.deb':'0bcaa1b1459f726f2c409f15697a0262740e2d94468624695a65a6d867f61439',
'policykit-1-gnome_0.105-7ubuntu5_arm64.deb':'79fe49479e18285eff0871a6a12a94323e54958adbd7628dd333f3a6eac96a70',
'libpolkit-agent-1-0_124-2ubuntu1.24.04.4_arm64.deb':'4e68630e08cafc284a1d8032390e520ed18cdcac34dfa906f76d0349585359ce'}
def checked_packages(directory):
 result={}
 for name,digest in PACKAGES.items():
  path=directory/name
  if path.is_symlink() or not path.is_file() or path.stat().st_size>2*1024*1024:raise ValueError('Pinned package missing or invalid')
  data=path.read_bytes()
  if hashlib.sha256(data).hexdigest()!=digest:raise ValueError('Pinned package integrity mismatch')
  result[name]=data
 return result
def outside_snapshot():
 result={}
 for path in ('/etc/passwd','/etc/group','/usr/bin/pkexec','/usr/lib/polkit-1/polkitd','/run/dbus/system_bus_socket'):
  p=Path(path);result[path]=hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else p.exists()
 for root in ('/etc/polkit-1','/usr/share/polkit-1'):
  p=Path(root);result[root]={str(q.relative_to(p)):hashlib.sha256(q.read_bytes()).hexdigest() for q in sorted(p.rglob('*')) if q.is_file()}
 return result
def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--packages',type=Path,required=True);args=parser.parse_args()
 if os.getuid()!=0:parser.error('Explicit private-namespace root provisioning is required.')
 if pwd.getpwnam(os.environ.get('LUDA_TEST_USER', 'desktop')).pw_uid!=1001:parser.error('Fixture requires existing ordinary UID1001.')
 for lookup,value in ((pwd.getpwnam,'polkitd'),(pwd.getpwuid,65530),(grp.getgrnam,'polkitd'),(grp.getgrgid,65530)):
  try:lookup(value)
  except KeyError:continue
  parser.error('Private test identity collides with an existing account/group.')
 packages=checked_packages(args.packages);out=ROOT/'artifacts/system-auth-private'/('run-'+str(time.time_ns()));out.mkdir(parents=True);(out/'rw').mkdir();(out/'packages').mkdir()
 for name,data in packages.items():(out/'packages'/name).write_bytes(data)
 before=outside_snapshot();source=source_fingerprint(ROOT);env=dict(os.environ,LUDA_PARENT_MOUNT_NS=os.readlink('/proc/self/ns/mnt'),LUDA_PARENT_NET_NS=os.readlink('/proc/self/ns/net'))
 result={'scope':'Private real authority/pkexec with custom cancel-only graphical agent; distro session agent checked separately','packages':PACKAGES,'source_before':source,'outside_before':before};started=time.monotonic()
 with (out/'output.log').open('w') as log:
  process=subprocess.Popen(['unshare','--mount','--pid','--fork','--mount-proc','--net','--kill-child','/bin/bash',str(ROOT/'tests/private_polkit_namespace.sh'),str(out),str(ROOT)],env=env,stdout=log,stderr=log,start_new_session=True)
  try:result['returncode']=process.wait(timeout=45)
  except subprocess.TimeoutExpired:
   result['timeout']=True;os.killpg(process.pid,signal.SIGKILL);result['returncode']=process.wait(timeout=5)
 result['seconds']=round(time.monotonic()-started,3);result['outside_after']=outside_snapshot();result['outside_unchanged']=before==result['outside_after'];result['source_after']=source_fingerprint(ROOT);result['source_unchanged']=source==result['source_after'];result['passed']=result['returncode']==0 and result['outside_unchanged'] and result['source_unchanged']
 (out/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'output':str(out),'passed':result['passed'],'seconds':result['seconds']}));return 0 if result['passed'] else 1
if __name__=='__main__':raise SystemExit(main())
