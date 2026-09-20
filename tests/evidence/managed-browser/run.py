#!/usr/bin/env python3
"""Launch the real probe on a new ordinary-user Xvfb/D-Bus desktop."""
import argparse
import os
from pathlib import Path
import signal
import subprocess
import json
import sys

HERE=Path(__file__).resolve().parent
def main(argv=None):
 parser=argparse.ArgumentParser(description=__doc__)
 parser.add_argument('--repo',type=Path,default=HERE.parents[2])
 parser.add_argument('--output',type=Path,required=True)
 parser.add_argument('--prefix',type=Path,required=True)
 parser.add_argument('--replace-owned-executable',type=Path)
 args=parser.parse_args(argv)
 if os.getuid()==0:raise SystemExit('Run as an ordinary test account; never use the shared desktop.')
 repo=args.repo.resolve();output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
 sys.path.insert(0,str(repo/'scripts'))
 from private_directory_cleanup import private_directory
 report={'status':'failed'}
 try:
  with private_directory(report,prefix='ld-test-') as private:
   env=dict(os.environ,LUDA_ISOLATED_TEST_DISPLAY='1',GSETTINGS_BACKEND='memory',NO_AT_BRIDGE='0')
   for variable,name in [('HOME','home'),('XDG_RUNTIME_DIR','runtime'),('XDG_CONFIG_HOME','config'),('XDG_DATA_HOME','data'),('XDG_CACHE_HOME','cache')]:
    path=Path(private)/name;path.mkdir(mode=0o700);env[variable]=str(path)
   env['XDG_CONFIG_DIRS']=env['XDG_CONFIG_HOME']
   channel=Path(env['XDG_CONFIG_HOME'])/'xfce4/xfconf/xfce-perchannel-xml';channel.mkdir(parents=True)
   (channel/'xfce4-session.xml').write_text('<?xml version="1.0"?><channel name="xfce4-session" version="1.0"><property name="general" type="empty"><property name="FailsafeSessionName" type="string" value="Failsafe"/><property name="SaveOnExit" type="bool" value="false"/></property><property name="startup" type="empty"><property name="ssh-agent" type="empty"><property name="enabled" type="bool" value="false"/></property><property name="gpg-agent" type="empty"><property name="enabled" type="bool" value="false"/></property></property><property name="sessions" type="empty"><property name="Failsafe" type="empty"><property name="IsFailsafe" type="bool" value="true"/><property name="Count" type="int" value="1"/><property name="Client0_Command" type="array"><value type="string" value="xfwm4"/></property><property name="Client0_Priority" type="int" value="15"/></property></property></channel>')
   for name in ('DISPLAY','WAYLAND_DISPLAY','DBUS_SESSION_BUS_ADDRESS','AT_SPI_BUS_ADDRESS'):env.pop(name,None)
   command=['xvfb-run','-a','-s','-screen 0 1440x900x24 -nolisten tcp','dbus-run-session','--',str(repo/'.venv/bin/python'),str(HERE/'probe.py'),'--prefix',str(args.prefix.resolve()),'--output',str(output)]
   if args.replace_owned_executable:command += ['--replace-owned-executable',str(args.replace_owned_executable.resolve())]
   with (output/'session.log').open('w') as log:
    process=subprocess.Popen(command,cwd=private,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    try:code=process.wait(timeout=90)
    finally:
     try:os.killpg(process.pid,signal.SIGTERM)
     except ProcessLookupError:pass
     try:process.wait(timeout=3)
     except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait(timeout=3)
   report.update(status='passed' if code==0 else 'failed',returncode=code)
 finally:
  (output/'private-directory-cleanup.json').write_text(json.dumps(report,indent=2))
 return code

if __name__=='__main__':raise SystemExit(main())
