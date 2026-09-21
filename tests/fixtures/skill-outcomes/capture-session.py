import os,sys,json,time,tempfile,uuid,subprocess,shutil,base64,hashlib
from pathlib import Path
ROOT=Path('/workspace/luda-screenshots');OUT=ROOT/'tests/fixtures/skill-outcomes'
sys.path.insert(0,str(ROOT/'scripts'))
from qualification_matrix import private_environment,run_bounded

def write(name,v): (OUT/name).write_text(json.dumps(v,indent=2)+'\n')
def setting(): return subprocess.check_output(['xfconf-query','-c','xsettings','-p','/Net/ThemeName'],text=True).strip()
def child():
 from luda.desktop import Desktop
 home=Path(os.environ['HOME']);shutil.copytree('/tmp/luda-greybird/usr/share/themes',home/'.themes')
 subprocess.run(['xfconf-query','-c','xsettings','-p','/Net/ThemeName','--create','--type','string','--set','Greybird'],check=True)
 children=[]
 for cmd in [['xfwm4','--compositor=off'],['xfsettingsd','--no-daemon']]: children.append(subprocess.Popen(cmd))
 time.sleep(1);subprocess.run(['xsetroot','-solid','#202020'],check=True)
 d=Desktop();states={}
 def launch(cmd):
  p=subprocess.Popen(cmd);children.append(p);time.sleep(2)
  wins=[w for w in d.list_windows() if w['pid']==p.pid];assert len(wins)==1,wins
  w=wins[0]['window_id'];d.activate(w);return w
 def row(w,name):
  nodes=d.inspect(w,limit=500)['nodes'];r=[n for n in nodes if n.get('name','').split('\n')[0]==name and n['role'] in ('table cell','icon')];assert len(r)==1,(name,nodes);return r[0]
 def capture(name,w,selected,applied,key):
  time.sleep(.5);obs=d.observe();png=base64.b64decode(obs.pop('image_base64'));(OUT/(name+'.png')).write_bytes(png)
  ins=d.inspect(w,limit=500);write(name+'.observe.json',obs);write(name+'.inspect.json',ins)
  oracle_code="""import gi,json
gi.require_version('Atspi','2.0')
from gi.repository import Atspi
result=[]
def walk(n):
 try:
  if n.get_state_set().contains(Atspi.StateType.SELECTED):result.append({'name':n.get_name(),'role':n.get_role_name()})
  for i in range(n.get_child_count()):walk(n.get_child_at_index(i))
 except Exception:pass
walk(Atspi.get_desktop(0))
print(json.dumps(result))
"""
  ax_selected=json.loads(subprocess.check_output(['/usr/bin/python3','-c',oracle_code],text=True));write(name+'.independent-selection.json',ax_selected)
  if selected: assert any(n['name'].split('\n')[0]==selected for n in ax_selected),ax_selected
  else: assert not any(n['name']=='target.txt' for n in ax_selected),ax_selected
  actual=setting();assert actual==applied,(actual,applied)
  selected_nodes=[n for n in ins['nodes'] if 'selected' in n.get('states',[])];print(name,selected_nodes,flush=True)
  states[key]={'png':name+'.png','observe':name+'.observe.json','inspect':name+'.inspect.json','sha256':hashlib.sha256(png).hexdigest(),'selected':selected,'applied':actual,'selected_nodes':selected_nodes,'window_id':w,'opened':False if name.startswith('file') else None}
 try:
  w=launch(['xfce4-appearance-settings']);write('doctor.json',d.doctor());write('windows.json',d.list_windows())
  capture('theme-light-selected-light',w,'Greybird','Greybird','theme:Greybird:Greybird')
  r=row(w,'Greybird-dark');write('choose-dark.json',d.element(r['element_id'],'choose'))
  capture('theme-dark-selected-light',w,'Greybird-dark','Greybird','theme:Greybird-dark:Greybird')
  r=row(w,'Greybird-dark');write('choose-dark-again.json',d.element(r['element_id'],'choose'));assert setting()=='Greybird';r=row(w,'Greybird-dark');write('invoke-dark.json',d.element(r['element_id'],'invoke',action='activate'));time.sleep(1)
  capture('theme-dark-selected-dark',w,'Greybird-dark','Greybird-dark','theme:Greybird-dark:Greybird-dark')
  children[-1].terminate();children[-1].wait(timeout=3)
  subprocess.run(['xfconf-query','-c','xsettings','-p','/Net/ThemeName','--set','Greybird'],check=True)
  w=launch(['thunar','/workspace/Selection trial']);subprocess.run(['xdotool','key','ctrl+2'],check=True);time.sleep(.5);capture('file-unselected',w,None,'Greybird','file::None')
  r=row(w,'target.txt');write('choose-file.json',d.element(r['element_id'],'choose'))
  capture('file-selected',w,'target.txt','Greybird','file:target.txt:None')
 finally:
  write('provenance.json',{'capture':'Real XFCE Appearance and Thunar on private Xvfb and DBus, ordinary ubuntu account, isolated HOME; unmodified scrot screenshot via Luda desktop_observe','source_commit':'eb268e820a9c96f2c934664b5edb18a0bd416c0a','theme_package':'https://ports.ubuntu.com/pool/universe/g/greybird-gtk-theme/greybird-gtk-theme_3.23.3-1_all.deb','states':states})
  d.close()
  for p in reversed(children):
   if p.poll() is None:p.terminate();p.wait(timeout=3)
if '--child' in sys.argv:child()
else:
 assert os.geteuid()!=0
 with tempfile.TemporaryDirectory(prefix='luda-fixture-capture-') as tmp:
  base=Path(tmp);token=uuid.uuid4().hex;env=private_environment(base,token);(base/'home').mkdir();env.update(HOME=str(base/'home'),XDG_CURRENT_DESKTOP='XFCE',LANG='C.UTF-8',LC_ALL='C.UTF-8',GTK_MODULES='gail:atk-bridge');env.pop('GTK_THEME',None)
  with (OUT/'capture.log').open('wb') as log:result=run_bounded(['xvfb-run','-a','-s','-screen 0 1024x768x24 -nolisten tcp','dbus-run-session','--',sys.executable,__file__,'--child'],env,log,90,token)
  write('runner.json',result);print(result)
