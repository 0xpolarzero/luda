#!/usr/bin/env python3
"""Generated per-VM plugin commands over private loopback SSH into two owned X11 sessions."""
import argparse, asyncio, hashlib, importlib.util, json, os, pathlib, pwd, shlex, signal, socket, subprocess, sys, time, uuid
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
ROOT=pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from build_plugin import build_host_marketplace, host_ssh_config
from qualify import source_fingerprint


def stop(process):
 if process.poll() is None:
  os.killpg(process.pid,signal.SIGTERM)
  try:process.wait(timeout=5)
  except subprocess.TimeoutExpired:os.killpg(process.pid,signal.SIGKILL);process.wait()


def session(out):
 # Executed as the dedicated desktop UID under private Xvfb and D-Bus.
 wm=subprocess.Popen(['xfce4-session'],start_new_session=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 fixture=None
 try:
  until=time.monotonic()+15
  while subprocess.run(['wmctrl','-m'],capture_output=True).returncode:
   assert wm.poll() is None and time.monotonic()<until;time.sleep(.1)
  fixture=subprocess.Popen(['/usr/bin/python3',str(ROOT/'tests/keyboard_fixture.py'),str(out)],start_new_session=True)
  (out/'session.json').write_text(json.dumps({'display':os.environ['DISPLAY'],'uid':os.getuid(),'fixture_pid':fixture.pid,'session_pid':wm.pid}))
  while not (out/'stop').exists():time.sleep(.1)
 finally:
  if fixture:stop(fixture)
  stop(wm)


async def probe(config, expected, own_state):
 async with stdio_client(StdioServerParameters(command=config['command'],args=config['args'],env=dict(os.environ))) as streams:
  async with ClientSession(*streams) as client:
   initialized=await client.initialize();assert initialized.serverInfo.name=='luda'
   tools=await client.list_tools();assert any(t.name=='desktop_observe' for t in tools.tools)
   response=await client.call_tool('desktop_doctor',{});assert not response.isError,response
   doctor=json.loads(response.content[0].text)
   assert doctor['ready'] and doctor['uid']==expected['uid'] and doctor['display']==expected['display'],doctor
   response=await client.call_tool('desktop_windows',{});assert not response.isError,response
   windows=json.loads(response.content[0].text)['windows'];assert any(w['pid']==expected['fixture_pid'] for w in windows),windows
   before=own_state.read_bytes()
   response=await client.call_tool('desktop_observe',{});assert not response.isError,response
   assert any(c.type=='image' for c in response.content)
   await asyncio.sleep(.15);assert own_state.read_bytes()==before
   return {'uid':doctor['uid'],'display':doctor['display'],'tool_count':len(tools.tools),'observed_owned_fixture':True,'image_returned':True,'widget_unchanged':True}


def main():
 parser=argparse.ArgumentParser();parser.add_argument('--output',type=pathlib.Path);parser.add_argument('--package-root',type=pathlib.Path);parser.add_argument('--session',type=pathlib.Path);args=parser.parse_args()
 if args.session:return session(args.session)
 assert os.getuid()==0
 out=args.output.resolve();out.mkdir(mode=0o755)
 package=args.package_root.resolve();env=dict(os.environ,LD_LIBRARY_PATH=':'.join(str(p) for p in (package/'usr/lib').glob('*-linux-gnu')))
 os.environ.update(LD_LIBRARY_PATH=env['LD_LIBRARY_PATH'])
 processes=[];directories=[];result={'status':'failed','source':source_fingerprint(ROOT),'cases':[]};token=uuid.uuid4().hex
 try:
  with (out/'install.log').open('w') as log:
   subprocess.run(['/usr/bin/python3',str(ROOT/'scripts/manage_install.py'),'install','--prefix',str(out/'install')],stdout=log,stderr=log,check=True,timeout=180)
  for label,user in [('alpha','daemon'),('beta','nobody')]:
   account=pwd.getpwnam(user);directory=out/label;directory.mkdir(mode=0o755);directories.append(directory)
   e=dict(env,HOME=str(directory),NO_AT_BRIDGE='0',GSETTINGS_BACKEND='memory',LUDA_HOST_PLUGIN_TEST_TOKEN=token)
   for key in ('DISPLAY','DBUS_SESSION_BUS_ADDRESS','XAUTHORITY','SESSION_MANAGER','WAYLAND_DISPLAY'):e.pop(key,None)
   for key in ('XDG_CONFIG_HOME','XDG_DATA_HOME','XDG_CACHE_HOME','XDG_RUNTIME_DIR'):
    path=directory/key;path.mkdir(mode=0o700);e[key]=str(path)
   e['XDG_CONFIG_DIRS']=e['XDG_CONFIG_HOME'];e['ICEAUTHORITY']=str(directory/'iceauth')
   for p in [directory,*directory.iterdir()]:os.chown(p,account.pw_uid,account.pw_gid)
   log=(out/(label+'.log')).open('w')
   p=subprocess.Popen(['runuser','-u',user,'--','xvfb-run','-a','-s','-screen 0 900x650x24 -nolisten tcp','dbus-run-session','--',sys.executable,str(__file__),'--session',str(directory)],env=e,start_new_session=True,stdout=log,stderr=log);processes.append(p)
   until=time.monotonic()+20
   while not (directory/'session.json').exists():
    assert p.poll() is None and time.monotonic()<until,(label,'session failed');time.sleep(.1)
  sshdir=out/'ssh literal $(touch SSH_INJECTION)';sshdir.mkdir(mode=0o755);os.chown(sshdir,1001,1001)
  for name in ('host','client'):subprocess.run([str(package/'usr/bin/ssh-keygen'),'-q','-t','ed25519','-N','','-f',str(sshdir/name)],env=env,check=True,timeout=5)
  (sshdir/'authorized_keys').write_text((sshdir/'client.pub').read_text());(sshdir/'authorized_keys').chmod(0o600)
  with socket.socket() as s:s.bind(('127.0.0.1',0));port=s.getsockname()[1]
  (sshdir/'known_hosts').write_text(f'[127.0.0.1]:{port} '+(sshdir/'host.pub').read_text())
  config=sshdir/'client config'
  allowed=[]
  for label,user in [('alpha','daemon'),('beta','nobody')]:
   prefix=out/(label+" prefix 'quoted' $(touch SSH_INJECTION)")
   allowed.append(host_ssh_config(prefix,user,package/'usr/bin/ssh',config,label)['mcpServers']['luda']['args'][-1])
  force=out/'force_exact_command.py'
  force.write_text("import os,sys\nallowed="+repr(allowed)+"\nif len(sys.argv)!=2 or sys.argv[1] not in allowed:raise SystemExit(64)\nos.execv('/bin/sh',['sh','-c',sys.argv[1]])\n")
  server_config=sshdir/'sshd_config' 
  server_config.write_text('\n'.join([f'Port {port}','ListenAddress 127.0.0.1','AddressFamily inet',f'HostKey "{sshdir/"host"}"',f'PidFile "{sshdir/"pid"}"',f'AuthorizedKeysFile "{sshdir/"authorized_keys"}"','UsePAM no','PasswordAuthentication no','KbdInteractiveAuthentication no','PubkeyAuthentication yes','StrictModes no','PermitRootLogin no','AllowUsers silo-desktop','AllowTcpForwarding no','AllowAgentForwarding no','X11Forwarding no','PermitUserRC no','ForceCommand /usr/bin/sudo -n /usr/bin/python3 '+shlex.quote(str(force))+' "$SSH_ORIGINAL_COMMAND"'])+'\n')
  for p in sshdir.iterdir():os.chown(p,1001,1001)
  sshlog=(out/'sshd.log').open('w')
  daemon=subprocess.Popen(['runuser','-u','silo-desktop','--',str(package/'usr/sbin/sshd'),'-D','-e','-f',str(server_config)],env=env,stdout=sshlog,stderr=sshlog,start_new_session=True);processes.append(daemon)
  time.sleep(.3);assert daemon.poll() is None
  config=sshdir/'client config';config.write_text('\n'.join(['Host alpha beta',' HostName 127.0.0.1',f' Port {port}',' User silo-desktop',f' IdentityFile "{sshdir/"client"}"',f' UserKnownHostsFile "{sshdir/"known_hosts"}"',' IdentitiesOnly yes',' LogLevel ERROR'])+'\n')
  for index,(label,user) in enumerate([('alpha','daemon'),('beta','nobody')],1):
   prefix=out/(label+" prefix 'quoted' $(touch SSH_INJECTION)");prefix.symlink_to(out/'install',target_is_directory=True)
   market=out/('market-'+label);skill=ROOT/'skills/luda/SKILL.md'
   build_host_marketplace(market,str(prefix),str(uuid.UUID(int=index)),skill,hashlib.sha256(skill.read_bytes()).hexdigest(),config,label,ssh_executable=package/'usr/bin/ssh',user=user)
   meta=json.loads((market/'host-registration.json').read_text());mcp=json.loads((market/'plugins'/meta['plugin']/'.mcp.json').read_text())['mcpServers'][meta['server_name']]
   directory=out/label;expected=json.loads((directory/'session.json').read_text())
   refused=subprocess.run([mcp['command'],*mcp['args'][:-1],'printf not-allowed'],env=env,capture_output=True,timeout=10)
   assert refused.returncode==64 and not refused.stdout, (refused.returncode,refused.stdout)
   proof=asyncio.run(asyncio.wait_for(probe(mcp,expected,directory/'state.json'),40));result['cases'].append({'alias':label,'server_name':meta['server_name'],'non_allowlisted_command_refused':True,**proof})
  assert result['cases'][0]['display']!=result['cases'][1]['display']
  assert not (ROOT/'SSH_INJECTION').exists() and not (out/'SSH_INJECTION').exists() and not pathlib.Path('/home/silo-desktop/SSH_INJECTION').exists()
  result['literal_paths_preserved']=True
  result['status']='passed'
 finally:
  for directory in directories:(directory/'stop').touch()
  for p in reversed(processes):stop(p)
  # Remove only invocation-tagged descendants across the two owned test UIDs.
  survivors=[]
  for p in pathlib.Path('/proc').iterdir():
   if not p.name.isdigit():continue
   try:
    if ('LUDA_HOST_PLUGIN_TEST_TOKEN='+token).encode() not in (p/'environ').read_bytes().split(b'\0'):continue
    os.kill(int(p.name),signal.SIGTERM);survivors.append(int(p.name))
   except (OSError,ProcessLookupError):pass
  time.sleep(.2)
  remaining=[]
  for pid in survivors:
   try:
    if ('LUDA_HOST_PLUGIN_TEST_TOKEN='+token).encode() in pathlib.Path(f'/proc/{pid}/environ').read_bytes().split(b'\0'):
     os.kill(pid,signal.SIGKILL);remaining.append(pid)
   except OSError:pass
  result['tagged_cleanup_pids']=survivors;result['cleanup_escalated_pids']=remaining;result['source_unchanged']=source_fingerprint(ROOT)==result['source']
  (out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
 print(json.dumps(result['cases'],indent=2))

if __name__=='__main__':main()
