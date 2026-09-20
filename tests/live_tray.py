"""MENU-07: real private XFCE tray, observed tooltip/menu and app counter oracle.

Fixed owned English fixture layout; the initial screenshot route was manually
reviewed. This is not general icon recognition or semantic tray ownership.
"""
import os,json,subprocess,time,sys,base64,tempfile,uuid
from pathlib import Path
from luda.desktop import Desktop
ROOT=Path(__file__).resolve().parents[1]

def child(out):
    p=Path(os.environ['XDG_CONFIG_HOME'])/'xfce4/xfconf/xfce-perchannel-xml';p.mkdir(parents=True)
    (p/'xfce4-panel.xml').write_text('''<channel name="xfce4-panel" version="1.0"><property name="configver" type="int" value="2"/><property name="panels" type="array"><value type="int" value="1"/><property name="panel-1" type="empty"><property name="position" type="string" value="p=6;x=0;y=0"/><property name="length" type="uint" value="100"/><property name="size" type="uint" value="36"/><property name="plugin-ids" type="array"><value type="int" value="1"/></property></property></property><property name="plugins" type="empty"><property name="plugin-1" type="string" value="systray"/></property></channel>''')
    children=[];d=None;result={}
    try:
     for cmd in (['xfwm4','--compositor=off'],['xfce4-panel','--disable-wm-check'],['/usr/bin/python3',str(ROOT/'tests/tray_fixture.py'),str(out)]):
      children.append(subprocess.Popen(cmd));time.sleep(.5)
     d=Desktop();time.sleep(2);result['windows']=[w for w in d.list_windows() if w['pid']==children[1].pid];assert len(result['windows'])==1;result['trees']=[]
     for w in result['windows']:
      try:result['trees'].append({'window':w,'tree':d.inspect(w['window_id'])})
      except Exception as exc:result['trees'].append({'window':w,'error':str(exc)})
     result['snapshot']=d.observe();result['oracle']=json.loads((out/'state.json').read_text());assert result['oracle']['embedded']
     try:
      result['hover']=d.hover(result['windows'][0]['window_id'],result['snapshot']['snapshot_id'],24,18)
      time.sleep(1);result['hover_snapshot']=d.observe()
     except Exception as exc:result['hover_error']={'code':getattr(exc,'code',None),'message':str(exc)}
     try:
      result['activate']=d.activate(result['windows'][0]['window_id'])
      snap=d.observe();result['focused_hover']=d.hover(result['windows'][0]['window_id'],snap['snapshot_id'],24,18)
      time.sleep(1);result['tooltip_snapshot']=d.observe()
      result['open_menu']=d.pointer(result['windows'][0]['window_id'],result['tooltip_snapshot']['snapshot_id'],24,18,button='right')
      time.sleep(.3);result['menu_snapshot']=d.observe();result['menu_tree']=d.inspect(result['windows'][0]['window_id'])
      result['menu_down']=d.key(result['windows'][0]['window_id'],'Down')
      result['menu_return']=d.key(result['windows'][0]['window_id'],'Return')
      deadline=time.monotonic()+3
      while time.monotonic()<deadline:
       result['final_oracle']=json.loads((out/'state.json').read_text())
       if result['final_oracle']['counter']==1:break
       time.sleep(.03)
      assert result['final_oracle']['counter']==1
     except Exception as exc:
      result['action_error']={'code':getattr(exc,'code',None),'message':str(exc)}
      raise
    finally:
     if d:d.close()
     for p in reversed(children):
      if p.poll() is None:
       p.terminate()
       try:p.wait(timeout=2)
       except subprocess.TimeoutExpired:p.kill();p.wait(timeout=2)
     for name in ('snapshot','tooltip_snapshot','menu_snapshot'):
      if name in result:
       (out/(name+'.png')).write_bytes(base64.b64decode(result[name].pop('image_base64')))
     (out/'results.json').write_text(json.dumps(result,indent=2))


def main():
    if os.geteuid()==0:raise SystemExit('Run as ordinary desktop account')
    if len(sys.argv)==3 and sys.argv[1]=='--child':return child(Path(sys.argv[2]))
    sys.path.insert(0,str(ROOT/'scripts'))
    from qualification_matrix import private_environment,run_bounded
    from qualify import source_fingerprint
    output=ROOT/'artifacts/tray'/str(time.time_ns());output.mkdir(parents=True)
    before=source_fingerprint(ROOT)
    with tempfile.TemporaryDirectory(prefix='luda-tray-session-') as directory:
        token=uuid.uuid4().hex;env=private_environment(Path(directory),token)
        with (output/'desktop.log').open('wb') as log:
            result=run_bounded(['xvfb-run','-a','dbus-run-session','--',sys.executable,__file__,'--child',str(output)],env,log,45,token)
    after=source_fingerprint(ROOT);result.update(source=before,source_after=after,source_unchanged=before==after)
    (output/'runner.json').write_text(json.dumps(result,indent=2));print(output,result['status'])
    return 0 if result['status']=='passed' and before==after else 1

if __name__=='__main__':raise SystemExit(main())
