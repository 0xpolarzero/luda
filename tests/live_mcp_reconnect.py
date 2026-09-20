"""Two private real XFCE sessions, one persistent stdio MCP connection."""
import asyncio
import json
import os
from pathlib import Path
import select
import signal
import subprocess
import sys
import tempfile
import time
import uuid
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

ROOT=Path(__file__).resolve().parents[1]


def child(out):
    wm=subprocess.Popen(['xfce4-session','--disable-tcp'])
    deadline=time.monotonic()+8
    while time.monotonic()<deadline:
        if wm.poll() is not None:raise RuntimeError('Private XFCE exited')
        if subprocess.run(['wmctrl','-m'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode==0:break
        time.sleep(.05)
    else:raise RuntimeError('Private XFCE readiness timeout')
    fixture=subprocess.Popen(['/usr/bin/python3',str(ROOT/'tests/fixture.py'),str(out)])
    (out/'session.json').write_text(json.dumps({'pid':wm.pid,'fixture':fixture.pid,'env':dict(os.environ)}))
    while True:time.sleep(1)


class PrivateSession:
    def __init__(self,base):
        self.base=base;self.process=None;self.xvfb=None;self.token=uuid.uuid4().hex
    def start(self):
        base=self.base;base.mkdir()
        config=base/'config';channel=config/'xfce4/xfconf/xfce-perchannel-xml';channel.mkdir(parents=True)
        (channel/'xfce4-session.xml').write_text('''<?xml version="1.0"?><channel name="xfce4-session" version="1.0"><property name="general" type="empty"><property name="FailsafeSessionName" type="string" value="Failsafe"/><property name="SaveOnExit" type="bool" value="false"/></property><property name="startup" type="empty"><property name="ssh-agent" type="empty"><property name="enabled" type="bool" value="false"/></property><property name="gpg-agent" type="empty"><property name="enabled" type="bool" value="false"/></property></property><property name="sessions" type="empty"><property name="Failsafe" type="empty"><property name="IsFailsafe" type="bool" value="true"/><property name="Count" type="int" value="1"/><property name="Client0_Command" type="array"><value type="string" value="xfwm4"/></property><property name="Client0_Priority" type="int" value="15"/></property></property></channel>''')
        runtime=base/'runtime';runtime.mkdir(mode=0o700)
        authority=base/'authority';authority.touch(mode=0o600)
        rd,wr=os.pipe()
        self.xvfb=subprocess.Popen(['Xvfb','-displayfd',str(wr),'-screen','0','900x700x24','-nolisten','tcp','-ac'],pass_fds=(wr,),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        os.close(wr)
        try:
            if not select.select([rd],[],[],5)[0]:raise RuntimeError('Private Xvfb timeout')
            display=':'+os.read(rd,32).decode().strip()
        finally:os.close(rd)
        env=dict(os.environ,DISPLAY=display,XAUTHORITY=str(authority),ICEAUTHORITY=str(base/'iceauthority'),XDG_RUNTIME_DIR=str(runtime),XDG_CONFIG_HOME=str(config),XDG_CONFIG_DIRS=str(config),XDG_CACHE_HOME=str(base/'cache'),XDG_DATA_HOME=str(base/'data'),GSETTINGS_BACKEND='memory',LUDA_RECONNECT_FIXTURE_TOKEN=self.token)
        for key in ('SESSION_MANAGER','DBUS_SESSION_BUS_ADDRESS'):env.pop(key,None)
        with (base/'session.log').open('w') as log:
            self.process=subprocess.Popen(['dbus-run-session','--',sys.executable,str(Path(__file__).resolve()),'--session',str(base)],env=env,stdout=log,stderr=log,start_new_session=True)
        deadline=time.monotonic()+12
        while time.monotonic()<deadline:
            if (base/'session.json').exists():
                self.info=json.loads((base/'session.json').read_text());return self
            if self.process.poll() is not None:raise RuntimeError((base/'session.log').read_text()[-1500:])
            time.sleep(.05)
        raise RuntimeError('Private session timeout')
    def terminate_session(self):
        if self.process and self.process.poll() is None:
            os.killpg(self.process.pid,signal.SIGTERM)
            try:self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:os.killpg(self.process.pid,signal.SIGKILL);self.process.wait(timeout=2)
        if self.xvfb and self.xvfb.poll() is None:self.xvfb.terminate();self.xvfb.wait(timeout=3)
    def close(self):
        self.terminate_session()
        marker=('LUDA_RECONNECT_FIXTURE_TOKEN='+self.token).encode()
        for p in Path('/proc').iterdir():
            if not p.name.isdigit():continue
            try:
                if p.stat().st_uid==os.getuid() and marker in (p/'environ').read_bytes().split(b'\0'):
                    os.kill(int(p.name),signal.SIGTERM)
            except OSError:pass


async def main():
    rows=[]
    with tempfile.TemporaryDirectory(prefix='luda-reconnect-live-') as directory:
        first=PrivateSession(Path(directory)/'first');second=PrivateSession(Path(directory)/'second')
        try:
            first.start();second.start()
            env=dict(first.info['env']);env.pop('LUDA_RECONNECT_FIXTURE_TOKEN',None)
            async with stdio_client(StdioServerParameters(command=sys.executable,args=['-m','luda.server'],env=env)) as streams:
                async with ClientSession(*streams) as session:
                    await session.initialize()
                    async def call(name,error=None,**arguments):
                        response=await session.call_tool(name,arguments)
                        value=json.loads(response.content[0].text)
                        if error:assert response.isError and value['code']==error,(name,value)
                        else:assert not response.isError,(name,value)
                        return value
                    async def owned(info):
                        for _ in range(60):
                            value=await call('desktop_windows')
                            found=next((w for w in value['windows'] if w['pid']==info['fixture']),None)
                            if found:return found
                            await asyncio.sleep(.05)
                        raise AssertionError('Owned window missing')
                    original=await owned(first.info)
                    shot=await call('desktop_observe')
                    tree=await call('desktop_inspect',window_id=original['window_id'])
                    old_element=next(n for n in tree['nodes'] if n['name']=='Contract text')['element_id']
                    await call('desktop_reconnect',error='SESSION_AMBIGUOUS')
                    assert (await owned(first.info))['window_id']==original['window_id']
                    rows.append('ambiguity-preserves-original-backend')
                    await call('desktop_reconnect',session_pid=2147483647,error='SESSION_NOT_FOUND')
                    assert (await owned(first.info))['window_id']==original['window_id']
                    rows.append('missing-session-preserves-original-backend')
                    first.terminate_session()
                    result=await call('desktop_reconnect',session_pid=second.info['pid'])
                    assert result['display']==second.info['env']['DISPLAY']
                    replacement=await owned(second.info)
                    await call('desktop_activate',window_id=original['window_id'],error='STALE_TARGET')
                    await call('desktop_read_text',element_id=old_element,error='STALE_TARGET')
                    await call('desktop_hover',window_id=replacement['window_id'],snapshot_id=shot['snapshot_id'],x=1,y=1,error='STALE_OBSERVATION')
                    await call('desktop_activate',window_id=replacement['window_id'])
                    fresh=await call('desktop_inspect',window_id=replacement['window_id'])
                    editor=next(n for n in fresh['nodes'] if n['name']=='Contract text')
                    payload='Persistent MCP after XFCE restart\n日本語 🔄\n'
                    await call('desktop_type',element_id=editor['element_id'],text=payload,mode='replace')
                    for _ in range(50):
                        if json.loads((second.base/'state.json').read_text())['text']==payload:break
                        await asyncio.sleep(.04)
                    else:raise AssertionError('Independent fixture readback mismatch')
                    rows.append('one-mcp-connection-survives-real-xfce-display-and-bus-loss')
                    await call('desktop_press_keys',window_id=replacement['window_id'],chord='ctrl+a')
                    pasted='Clipboard routed to replacement display\n'
                    await call('desktop_paste',window_id=replacement['window_id'],text=pasted,shortcut='ctrl_v')
                    for _ in range(50):
                        if json.loads((second.base/'state.json').read_text())['text']==pasted:break
                        await asyncio.sleep(.04)
                    else:raise AssertionError('Clipboard targeted wrong backend environment')
                    rows.append('clipboard-process-inherits-replacement-backend-environment')
                    await call('desktop_status')
                    await call('desktop_control',action='pause')
                    await call('desktop_reconnect',session_pid=second.info['pid'])
                    assert (await call('desktop_control'))['paused']
                    await call('desktop_control',action='resume')
                    rows.append('reconnect-does-not-bypass-display-pause')
                    assert (await call('desktop_doctor'))['display']==second.info['env']['DISPLAY']
        finally:second.close();first.close()
    print(json.dumps({'passed':rows},indent=2))


if __name__=='__main__':
    if len(sys.argv)>1 and sys.argv[1]=='--session':child(Path(sys.argv[2]))
    else:asyncio.run(main())
