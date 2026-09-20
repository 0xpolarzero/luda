"""Actual locked-wheel root install under umask077, with independent UID proof."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import signal
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--user', required=True, help='Existing ordinary Linux test account')
    parser.add_argument('--prefix',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if os.getuid()!=0:parser.error('This qualification requires root and the explicit existing ordinary account.')
    account=pwd.getpwnam(args.user)
    if args.prefix.exists() or args.output.exists():parser.error('Use fresh prefix and evidence paths.')
    args.output.mkdir(mode=0o700)
    source_files=[ROOT/'scripts/manage_install.py',ROOT/'scripts/install.sh']
    before={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files}
    with (args.output/'install.log').open('w') as log:
        child=subprocess.Popen(['/bin/bash',str(ROOT/'scripts/install.sh'),str(args.prefix),'--skip-system','--user',account.pw_name],
            stdout=log,stderr=subprocess.STDOUT,umask=0o077,start_new_session=True)
        try:assert child.wait(timeout=600)==0,'Actual installer failed; see retained log.'
        finally:
            try:os.killpg(child.pid,signal.SIGKILL)
            except ProcessLookupError:pass
            child.wait(timeout=5)
    release=(args.prefix/'current').resolve(strict=True)
    code='''import hashlib,json,os,pathlib,sys,luda.server,luda.session
root=pathlib.Path(sys.argv[1]);package=pathlib.Path(luda.server.__file__).resolve().parent
assert package.is_relative_to(root/'.venv')
skill=(root/'skills/luda/SKILL.md').read_bytes()
assert skill
print(json.dumps({'uid':os.getuid(),'package':str(package),'skill_sha256':hashlib.sha256(skill).hexdigest(),'modules':{str(p.relative_to(package)):hashlib.sha256(p.read_bytes()).hexdigest() for p in package.rglob('*.py')}}))
'''
    result=subprocess.run([str(release/'.venv/bin/python'),'-I','-c',code,str(release)],
        user=account.pw_uid,group=account.pw_gid,extra_groups=os.getgrouplist(account.pw_name,account.pw_gid),
        cwd='/',env={'PATH':'/usr/bin:/bin','HOME':account.pw_dir,'LANG':'C.UTF-8'},capture_output=True,text=True,timeout=30,check=True)
    proof=json.loads(result.stdout);assert proof['uid']==account.pw_uid
    expected={str(p.relative_to(ROOT/'src/luda')):hashlib.sha256(p.read_bytes()).hexdigest() for p in (ROOT/'src/luda').rglob('*.py')}
    assert proof['modules']==expected
    assert proof['skill_sha256']==hashlib.sha256((ROOT/'skills/luda/SKILL.md').read_bytes()).hexdigest()
    assert before=={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source_files}
    proof.update(installed=True,release=release.name,umask='077',source_unchanged=True,installer_sources=before,
        scope='Actual locked default wheel installation and isolated desktop-account imports/skill reads; no GUI claim.')
    (args.output/'result.json').write_text(json.dumps(proof,indent=2)+'\n')
    print(json.dumps({'installed':True,'uid':proof['uid'],'modules':len(expected),'release':release.name}))

if __name__=='__main__':main()
