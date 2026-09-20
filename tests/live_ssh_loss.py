"""Real loopback SSH loss after observed input starts; extracted test binaries only."""
import argparse,asyncio,json,os,pwd,re,shlex,socket,subprocess,sys,tempfile,time,uuid
from pathlib import Path
from live_mcp_disconnect import Client as PipeClient,wait,process_identities,alive
from live_keyboard_guard import Oracle
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from qualification_matrix import private_environment,cleanup_owned
from headless_tests import stop
from qualify import source_fingerprint

class SSHClient(PipeClient):
 def __init__(self,label,command,env,out):
  super().__init__(label);self.command=command;self.env=env;self.out=out;self.remote=None
 async def start(self):
  self.log=(self.out/(self.label+'-ssh.log')).open('w')
  self.process=await asyncio.create_subprocess_exec(*self.command,self.label,env=self.env,stdin=asyncio.subprocess.PIPE,stdout=asyncio.subprocess.PIPE,stderr=self.log,start_new_session=True)
  self.task=asyncio.create_task(self.read())
  await self.request('initialize',{'protocolVersion':'2025-03-26','capabilities':{},'clientInfo':{'name':'luda-ssh-loss-fixture','version':'1'}})
  await self.send({'jsonrpc':'2.0','method':'notifications/initialized'})
  self.remote=json.loads((self.out/(self.label+'.pid.json')).read_text())
  return self
 async def disconnect(self):
  self.process.kill()  # Actual SSH client SIGKILL: both transport directions lost.
  await self.process.wait();await asyncio.wait_for(self.task,3)
  assert self.process.returncode==-9
 async def remote_exited(self):
  await wait(lambda:not alive({self.remote['pid']:self.remote['start']}),timeout=12)
 async def close(self):
  if self.process and self.process.returncode is None:
   self.process.stdin.close()
   try:await asyncio.wait_for(self.process.wait(),5)
   except asyncio.TimeoutError:self.forced_shutdown=True;self.process.kill();await self.process.wait()
  if self.remote:
   try:await self.remote_exited()
   except RuntimeError:self.forced_shutdown=True
  if self.task and not self.task.done():self.task.cancel()
  if hasattr(self,'log'):self.log.close()

async def cases(command,env,out):
 records=[];clients=[];fixture=None;oracle=None
 def record(case,passed,**details):
  row=dict(case=case,passed=bool(passed),**details);records.append(row);print(json.dumps(row),flush=True)
  assert passed,row
 def state():return json.loads((out/'state.json').read_text())
 async def new(label):
  client=SSHClient(label,command,env,out);clients.append(client);return await client.start()
 async def target(client):
  deadline=time.monotonic()+5
  while time.monotonic()<deadline:
   windows=(await client.call('desktop_windows'))['windows'];owner=next((w for w in windows if w['pid']==fixture.pid),None)
   if owner:return owner['window_id']
   await asyncio.sleep(.05)
  raise RuntimeError('Owned fixture unavailable')
 try:
  fixture=subprocess.Popen(['/usr/bin/python3',str(ROOT/'tests/disconnect_fixture.py'),str(out)],stdout=subprocess.DEVNULL,stderr=(out/'fixture.log').open('w'))
  oracle=Oracle();client=await new('keys');wid=await target(client);await client.call('desktop_activate',window_id=wid)
  await wait(lambda:(out/'state.json').exists())
  pending=await client.begin('tools/call',{'name':'desktop_press_keys','arguments':{'window_id':wid,'chord':'a','count':20}})
  await wait(lambda:oracle.code('a') in oracle.pressed())
  helpers=process_identities(client.remote['pid']);began=time.monotonic()
  record('real-key-down-before-ssh-client-loss',not pending.done(),remote=client.remote,helpers=helpers)
  await client.disconnect();await client.remote_exited();await wait(lambda:not oracle.pressed() and not oracle.buttons())
  await asyncio.sleep(.2);text=state()['text']
  record('ssh-loss-releases-input-and-remote-helpers',not alive(helpers),seconds=round(time.monotonic()-began,3),surviving_helpers=alive(helpers),ssh_exit_code=client.process.returncode)
  record('partial-key-effect-without-replay',text=='a'*len(text) and 1<=len(text)<=20,characters_after_loss=len(text),request_count=20,response_received=pending.done())
  fresh=await new('after-keys');status=await fresh.call('desktop_status');await asyncio.sleep(.4)
  record('new-ssh-session-does-not-replay-keys',state()['text']==text and status['operations']==[])
  newwid=await target(fresh);await fresh.call('desktop_activate',window_id=newwid);await fresh.call('desktop_press_keys',window_id=newwid,chord='z')
  await wait(lambda:state()['text']==text+'z');record('new-ssh-explicit-key-only',True);await fresh.close()
  action=await new('action');awid=await target(action);await action.call('desktop_activate',window_id=awid)
  tree=await action.call('desktop_inspect',window_id=awid);button=next(n for n in tree['nodes'] if n['name']=='Run gated action')
  pending_action=await action.begin('tools/call',{'name':'desktop_invoke','arguments':{'element_id':button['element_id']}})
  await wait(lambda:(out/'started').exists());helpers=process_identities(action.remote['pid'])
  record('application-action-started-before-ssh-loss',state()['started']==1 and state()['completed']==0 and not pending_action.done(),remote=action.remote,helpers=helpers)
  began=time.monotonic();await action.disconnect();await asyncio.sleep(.1);(out/'release').write_text('explicit test gate release after real transport loss')
  await action.remote_exited();await wait(lambda:state()['completed']==1)
  record('delivered-action-finishes-once-after-ssh-loss',state()['started']==1 and state()['completed']==1,late_effect=True,undo_claimed=False)
  record('action-remote-server-and-helpers-exit',not alive(helpers),seconds=round(time.monotonic()-began,3),ssh_exit_code=action.process.returncode,surviving_helpers=alive(helpers))
  final=await new('after-action');status=await final.call('desktop_status');await asyncio.sleep(.4)
  record('fresh-ssh-session-does-not-replay-action',state()['started']==1 and state()['completed']==1 and status['operations']==[])
  finalwid=await target(final);tree=await final.call('desktop_inspect',window_id=finalwid);button=next(n for n in tree['nodes'] if n['name']=='Run gated action')
  await final.call('desktop_invoke',element_id=button['element_id']);await wait(lambda:state()['completed']==2)
  record('fresh-ssh-explicit-action-only',state()['started']==2 and state()['completed']==2)
 except Exception as exc:
  records.append({'case':'harness-failure','passed':False,'error_type':type(exc).__name__,'message':str(exc)})
 finally:
  (out/'release').write_text('cleanup release')
  for client in reversed(clients):
   await client.close()
   if client.forced_shutdown:records.append({'case':'forced-harness-cleanup','passed':False,'client':client.label})
  if oracle:oracle.close()
  if fixture and fixture.poll() is None:fixture.terminate();fixture.wait(timeout=3)
 return records


def remote(out):
 label=os.environ.get('SSH_ORIGINAL_COMMAND','')
 if not re.fullmatch('[a-z-]{1,30}',label):raise SystemExit('Invalid owned session label')
 start=Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]
 (out/(label+'.pid.json')).write_text(json.dumps({'pid':os.getpid(),'start':start,'uid':os.getuid()}))
 os.execv(sys.executable,[sys.executable,'-m','luda.server'])


def child(package_root,out):
 source=source_fingerprint(ROOT);wm=None;server=None;result={'status':'failed','uid':os.getuid()}
 env=dict(os.environ,LD_LIBRARY_PATH=':'.join(str(path) for path in (package_root/'usr/lib').glob('*-linux-gnu') if path.is_dir()))
 try:
  with tempfile.TemporaryDirectory(prefix='luda-private-sshd-') as directory:
   root=Path(directory)
   for name in ('host','client'):
    subprocess.run([str(package_root/'usr/bin/ssh-keygen'),'-q','-t','ed25519','-N','','-f',str(root/name)],env=env,check=True,capture_output=True,timeout=5)
   (root/'authorized_keys').write_text((root/'client.pub').read_text());(root/'authorized_keys').chmod(0o600)
   with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
   (root/'known_hosts').write_text(f'[127.0.0.1]:{port} '+(root/'host.pub').read_text())
   retained=('DISPLAY','XAUTHORITY','DBUS_SESSION_BUS_ADDRESS','XDG_CONFIG_HOME','XDG_DATA_HOME','XDG_CACHE_HOME','XDG_RUNTIME_DIR','XDG_CONFIG_DIRS','GSETTINGS_BACKEND','NO_AT_BRIDGE','LUDA_ISOLATED_TEST_DISPLAY','LUDA_MATRIX_PROCESS_TOKEN')
   launcher=shlex.join(['/usr/bin/env',*[key+'='+env[key] for key in retained if key in env],sys.executable,str(Path(__file__).resolve()),'--remote-server',str(out)])
   config='\n'.join([f'Port {port}','ListenAddress 127.0.0.1','AddressFamily inet',f'HostKey {root/"host"}',f'PidFile {root/"pid"}',f'AuthorizedKeysFile {root/"authorized_keys"}',
     'StrictModes no','UsePAM no','PasswordAuthentication no','KbdInteractiveAuthentication no','PermitRootLogin no','PubkeyAuthentication yes','AllowTcpForwarding no','AllowAgentForwarding no','X11Forwarding no','PermitTunnel no','PermitUserRC no',f'AllowUsers {pwd.getpwuid(os.getuid()).pw_name}','ForceCommand '+launcher])+'\n'
   (root/'config').write_text(config)
   with (out/'sshd.log').open('w') as sshlog,(out/'desktop.log').open('w') as desktoplog:
    wm=subprocess.Popen(['xfwm4','--compositor=off'],stdout=desktoplog,stderr=desktoplog)
    deadline=time.monotonic()+5
    while subprocess.run(['wmctrl','-m'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:
     assert time.monotonic()<deadline;time.sleep(.05)
    server=subprocess.Popen([str(package_root/'usr/sbin/sshd'),'-D','-e','-f',str(root/'config')],env=env,stdout=subprocess.DEVNULL,stderr=sshlog)
    time.sleep(.2);assert server.poll() is None,(out/'sshd.log').read_text()
    command=[str(package_root/'usr/bin/ssh'),'-T','-F','/dev/null','-p',str(port),'-i',str(root/'client'),'-o','IdentitiesOnly=yes','-o','IdentityAgent=none','-o','BatchMode=yes','-o','PasswordAuthentication=no','-o','KbdInteractiveAuthentication=no','-o','StrictHostKeyChecking=yes','-o',f'UserKnownHostsFile={root/"known_hosts"}','-o','GlobalKnownHostsFile=/dev/null','-o','ConnectTimeout=3',pwd.getpwuid(os.getuid()).pw_name+'@127.0.0.1']
    began=time.monotonic();records=asyncio.run(cases(command,env,out))
    result.update(status='passed' if records and all(row['passed'] for row in records) else 'failed',cases=records,seconds=time.monotonic()-began,
      ssh_version=subprocess.run([str(package_root/'usr/bin/ssh'),'-V'],env=env,capture_output=True,text=True,timeout=3).stderr.strip(),loopback_address='127.0.0.1',port=port,
      strict_modes='disabled only for owned 0700 temporary key directory under /tmp',authentication='generated public key only; no PAM/password/agent or forwarding')
 finally:
  for process in (server,wm):
   if process and process.poll() is None:process.terminate();process.wait(timeout=3)
  after=source_fingerprint(ROOT);result.update(source_before=source,source_after=after,source_unchanged=source==after)
  if source!=after:result['status']='source_changed'
  (out/'results.json').write_text(json.dumps(result,indent=2)+'\n')
 return 0 if result['status']=='passed' else 1


def main():
 parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--package-root',type=Path);parser.add_argument('--output',type=Path);parser.add_argument('--child',action='store_true');parser.add_argument('--remote-server',type=Path);args=parser.parse_args()
 if args.remote_server:return remote(args.remote_server)
 if os.getuid()==0:parser.error('Run as ordinary desktop user.')
 if not args.package_root:parser.error('--package-root with extracted official distro OpenSSH packages is required')
 package_root=args.package_root.resolve();out=(args.output or ROOT/'artifacts/ssh-loss'/('run-'+str(time.time_ns()))).resolve();out.mkdir(parents=True,exist_ok=True)
 if args.child:return child(package_root,out)
 token=str(uuid.uuid4())
 with tempfile.TemporaryDirectory(prefix='luda-private-ssh-display-') as directory:
  env=private_environment(Path(directory),token)
  with (out/'harness.log').open('w') as log:
   process=subprocess.Popen(['xvfb-run','-a','-s','-screen 0 1200x900x24 -nolisten tcp','dbus-run-session','--',sys.executable,__file__,'--child','--package-root',str(package_root),'--output',str(out)],env=env,stdout=log,stderr=log,start_new_session=True)
   try:code=process.wait(timeout=100)
   finally:stop(process);cleanup=cleanup_owned(token);(out/'cleanup.json').write_text(json.dumps(cleanup,indent=2)+'\n')
  assert not cleanup['survivors'],cleanup
 print(json.dumps({'output':str(out),'returncode':code,'cleanup':cleanup}));return code

if __name__=='__main__':raise SystemExit(main())
