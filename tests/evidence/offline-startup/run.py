"""Root harness creates only a private network namespace; GUI runs as selected user."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import pwd
import socket
import subprocess
import sys
import threading

ROOT=Path(__file__).resolve().parents[3]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--release',type=Path,required=True)
    p.add_argument('--user',required=True)
    p.add_argument('--output',type=Path,required=True)
    args=p.parse_args()
    if os.getuid()!=0:p.error('Private network-namespace setup requires root; GUI always drops to --user.')
    account=pwd.getpwnam(args.user)
    if account.pw_uid==0:p.error('Select an ordinary GUI account.')
    source_paths=[Path(__file__),Path(__file__).with_name('probe.py'),ROOT/'tests/fixture.py',ROOT/'scripts/ci_stage.py']
    source_before={str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest() for path in source_paths}
    release=args.release.resolve(strict=True);output=args.output.resolve()
    output.mkdir(parents=True,exist_ok=False);os.chown(output,account.pw_uid,account.pw_gid)
    environment={'PATH':'/usr/bin:/bin','LANG':'C.UTF-8','NO_AT_BRIDGE':'0','GSETTINGS_BACKEND':'memory','LUDA_ISOLATED_TEST_DISPLAY':'1'}
    for variable,name in [('HOME','home'),('XDG_RUNTIME_DIR','run'),('XDG_CONFIG_HOME','config'),('XDG_DATA_HOME','data'),('XDG_CACHE_HOME','cache')]:
        directory=output/name;directory.mkdir(mode=0o700);os.chown(directory,account.pw_uid,account.pw_gid);environment[variable]=str(directory)
    environment['XDG_CONFIG_DIRS']=environment['XDG_CONFIG_HOME']
    channel=output/'config/xfce4/xfconf/xfce-perchannel-xml';channel.mkdir(parents=True)
    for directory in [channel,*channel.parents]:
        if directory==output:break
        os.chown(directory,account.pw_uid,account.pw_gid)
    (channel/'xfce4-session.xml').write_text('<channel name="xfce4-session" version="1.0"><property name="general" type="empty"><property name="FailsafeSessionName" type="string" value="Failsafe"/><property name="SaveOnExit" type="bool" value="false"/></property><property name="startup" type="empty"><property name="ssh-agent" type="empty"><property name="enabled" type="bool" value="false"/></property><property name="gpg-agent" type="empty"><property name="enabled" type="bool" value="false"/></property></property><property name="sessions" type="empty"><property name="Failsafe" type="empty"><property name="IsFailsafe" type="bool" value="true"/><property name="Count" type="int" value="1"/><property name="Client0_Command" type="array"><value type="string" value="xfwm4"/></property><property name="Client0_Priority" type="int" value="15"/></property></property></channel>')
    listener=socket.socket();listener.bind(('127.0.0.1',0));listener.listen();accepted=threading.Event()
    def canary():
        connection,_=listener.accept();connection.close();accepted.set()
    thread=threading.Thread(target=canary,daemon=True);thread.start()
    with socket.create_connection(listener.getsockname(),timeout=1):pass
    assert accepted.wait(1),'Host canary not independently reachable'
    namespace=os.readlink('/proc/self/ns/net')
    command=['unshare','--net','--','runuser','-u',args.user,'--','env','-i',*[key+'='+value for key,value in environment.items()],
             'xvfb-run','-a','-s','-screen 0 1200x900x24 -nolisten tcp','dbus-run-session','--',str(release/'.venv/bin/python'),'-I',str(Path(__file__).with_name('probe.py')),
             '--release',str(release),'--output',str(output),'--host-namespace',namespace,'--host-port',str(listener.getsockname()[1])]
    try:
        with (output/'session.log').open('w') as log:
            result=subprocess.run([sys.executable,str(ROOT/'scripts/ci_stage.py'),'--timeout','75','--evidence',str(output/'cleanup.json'),'--',*command],stdout=log,stderr=subprocess.STDOUT)
        proof=json.loads((output/'cleanup.json').read_text())
        assert result.returncode==0 and proof['cleanup_confirmed'],proof
        source_after={str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest() for path in source_paths}
        assert source_before==source_after,'Fixture source changed during qualification'
        (output/'fixture-source.json').write_text(json.dumps({'before':source_before,'after':source_after,'unchanged':True},indent=2)+'\n')
        print(json.dumps({'passed':True,'release':release.name,'output':str(output),'host_canary_reachable_before_isolation':True,'cleanup_confirmed':True}))
    finally:listener.close();thread.join(timeout=1)

if __name__=='__main__':main()
