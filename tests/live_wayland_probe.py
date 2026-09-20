#!/usr/bin/env python3
"""Private Weston/Xwayland diagnostic probe; run inside an ordinary-UID private D-Bus session.

Argument: fresh owned output directory containing a mode0700 runtime subdirectory.
Set XDG_RUNTIME_DIR there and use a Python interpreter with Luda dependencies.
Requires explicit unsupported-backend refusal for pure Wayland and Xwayland, and a working native X11 display despite stale Wayland hints.
"""
import os,subprocess,time,pathlib,json,re,signal,sys,asyncio
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
ROOT=pathlib.Path(__file__).resolve().parents[1]
assert os.getuid()!=0, 'Run as the ordinary desktop account in a private session'
root=pathlib.Path(sys.argv[1]);env=dict(os.environ);env.pop('DISPLAY',None);env.pop('XAUTHORITY',None);env.update(XDG_SESSION_TYPE='wayland',WAYLAND_DISPLAY='luda-wayland')
children=[]
def start(argv,**kw):
 p=subprocess.Popen(argv,env=env,start_new_session=True,**kw);children.append(p);return p
async def mcp_refusals(scene):
 params=StdioServerParameters(command=sys.executable,args=['-m','luda.server'],env=dict(env))
 rows=[]
 async with stdio_client(params) as streams:
  async with ClientSession(*streams) as session:
   await session.initialize()
   for name,args in [('desktop_observe',{}),('desktop_windows',{}),('desktop_press_keys',{'window_id':'unknown-owned-probe-target','chord':'a'}),('desktop_launch',{'application_id':'unknown-owned-probe-application'})]:
    response=await session.call_tool(name,args)
    value=json.loads(response.content[0].text)
    rows.append({'tool':name,'code':value.get('code'),'effect':value.get('effect')})
    assert response.isError and value.get('code')=='UNSUPPORTED_BACKEND' and value.get('effect')=='none', (scene,rows)
 return rows
try:
 p=start(['weston','--backend=headless','--renderer=pixman','--socket=luda-wayland','--idle-time=0','--xwayland','--log='+str(root/'weston.log')],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 for _ in range(100):
  text=(root/'weston.log').read_text() if (root/'weston.log').exists() else ''
  match=re.search(r'xserver listening on display (:[0-9]+)',text)
  if match:break
  if p.poll() is not None:raise RuntimeError(text)
  time.sleep(.1)
 assert match,text
 display=match[1];assert display!=':1',display
 result={'weston_version':subprocess.check_output(['weston','--version'],text=True).strip(),'xwayland_display':display}
 def invoke(label, extra):
  e=dict(env);e.update(extra)
  code='''import json\nfrom luda.desktop import Desktop\nfrom luda.common import DesktopError\nd=Desktop();out={}\nfor name in ('doctor','observe'):\n try:\n  with d.transaction():value=getattr(d,name)()\n  value.pop('image_base64',None);out[name]=value\n except DesktopError as exc:out[name]={'code':exc.code,'effect':exc.effect,'message':str(exc)}\nd.close();print(json.dumps(out))'''
  out=subprocess.run([sys.executable,'-c',code],env=e,capture_output=True,text=True,timeout=40)
  (root/(label+'.stderr')).write_text(out.stderr);assert out.returncode==0,out.stderr
  result[label]=json.loads(out.stdout)
  doctor=result[label]['doctor']
  assert doctor.get('ready') is False and doctor.get('display_error_code')=='UNSUPPORTED_BACKEND', (label,doctor)
  result[label]['mcp']=asyncio.run(asyncio.wait_for(mcp_refusals(label),30))
 invoke('pure_wayland',{})
 env['DISPLAY']=display
 env['GDK_BACKEND']='x11'
 x=start(['xterm','-title','Luda Owned Xwayland Probe','-e','/bin/sleep','120'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 for _ in range(100):
  out=subprocess.run(['xdpyinfo','-queryExtensions'],env=env,capture_output=True,text=True)
  if out.returncode==0:break
  time.sleep(.1)
 (root/'extensions.txt').write_text(out.stdout);assert out.returncode==0,out.stderr
 fixture=start(['/usr/bin/python3',str(ROOT/'tests/keyboard_fixture.py'),str(root)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 for _ in range(100):
  if (root/'state.json').exists():break
  time.sleep(.1)
 invoke('xwayland',{})
 code='''import json
from luda.desktop import Desktop
from luda.common import DesktopError
d=Desktop();out={}
try:
 with d.transaction():
  windows=d.list_windows();out['windows']=windows;w=next(w for w in windows if w['pid']==FIXTURE_PID);out['activate']=d.activate(w['window_id']);out['key']=d.key(w['window_id'],'a')
except DesktopError as exc:out['error']={'code':exc.code,'effect':exc.effect,'message':str(exc)}
except StopIteration:out['error']={'code':'PROBE_NO_OWNED_WINDOW'}
finally:d.close()
print(json.dumps(out))'''.replace('FIXTURE_PID',str(fixture.pid))
 mutation=subprocess.run([sys.executable,'-c',code],env=env,capture_output=True,text=True,timeout=30)
 assert mutation.returncode==0,mutation.stderr
 time.sleep(.1);result['mutation']=json.loads(mutation.stdout);result['independent_widget']=json.loads((root/'state.json').read_text())
 env.pop('XDG_SESSION_TYPE');env.pop('WAYLAND_DISPLAY');invoke('xwayland_no_hints',{})
 time.sleep(.15)
 assert json.loads((root/'state.json').read_text())==result['independent_widget'], 'Unexpected late input'
 assert result['independent_widget']['text']=='' and result['independent_widget']['events']==[]
 # A separate native X server must not be rejected solely by stale hints.
 readfd,writefd=os.pipe()
 native=start(['Xvfb','-displayfd',str(writefd),'-screen','0','800x600x24','-nolisten','tcp'],pass_fds=(writefd,),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 os.close(writefd)
 import select
 assert select.select([readfd],[],[],5)[0], 'Native Xvfb startup timed out'
 native_display=':'+os.read(readfd,32).decode().strip();os.close(readfd);assert native_display not in (':1',display)
 env.update(DISPLAY=native_display,XDG_SESSION_TYPE='wayland',WAYLAND_DISPLAY='stale-owned-probe')
 out=subprocess.run(['xdpyinfo','-queryExtensions'],env=env,capture_output=True,text=True,timeout=5);assert out.returncode==0 and 'XWAYLAND' not in out.stdout
 (root/'native-extensions.txt').write_text(out.stdout)
 code="from luda.desktop import Desktop;import json;d=Desktop();r=d.doctor();d.require_supported_backend();r['backend_accepted']=True;d.close();print(json.dumps(r))"
 out=subprocess.run([sys.executable,'-c',code],env=env,capture_output=True,text=True,timeout=30);assert out.returncode==0,out.stderr
 result['native_x11_stale_hints']=json.loads(out.stdout);assert result['native_x11_stale_hints']['display_available'] is True
 (root/'result.json').write_text(json.dumps(result,indent=2))
 print(json.dumps({'passed':True,'scenes':['pure_wayland','xwayland','xwayland_no_hints','native_x11_stale_hints'],'mcp_refusals':12}))
finally:
 for p in reversed(children):
  if p.poll() is None:
   os.killpg(p.pid,signal.SIGTERM)
   try:p.wait(timeout=3)
   except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
