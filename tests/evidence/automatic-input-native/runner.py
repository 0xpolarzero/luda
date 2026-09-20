import json, os, subprocess, sys, tempfile, time
from pathlib import Path
root=Path(sys.argv[1]).resolve();out=root/'artifacts/automatic-input-native'
out.mkdir(parents=True,exist_ok=True)
source=subprocess.check_output(['git','-c',f'safe.directory={root}','-C',str(root),'rev-parse','HEAD'],text=True).strip()
assert os.getuid()==1000 and os.environ.get('LUDA_ISOLATED_TEST_DISPLAY')=='1' and os.environ['DISPLAY']!=':1'
results=[]
with tempfile.TemporaryDirectory(prefix='luda-native-validation-') as directory:
 for key in ('XDG_CONFIG_HOME','XDG_DATA_HOME','XDG_CACHE_HOME','XDG_RUNTIME_DIR'):
  p=Path(directory)/key;p.mkdir(mode=0o700);os.environ[key]=str(p)
 os.environ.update(GSETTINGS_BACKEND='memory',NO_AT_BRIDGE='0',GTK_A11Y='atspi',QT_ACCESSIBILITY='1',QT_LINUX_ACCESSIBILITY_ALWAYS_ON='1')
 subprocess.run(['dbus-update-activation-environment','XDG_CONFIG_HOME','XDG_DATA_HOME','XDG_CACHE_HOME','XDG_RUNTIME_DIR','GSETTINGS_BACKEND'],check=True)
 with (out/'wm.log').open('w') as log: wm=subprocess.Popen(['xfwm4','--compositor=off'],stdout=log,stderr=log)
 try:
  end=time.monotonic()+8
  while subprocess.run(['wmctrl','-m'],capture_output=True).returncode:
   assert time.monotonic()<end;time.sleep(.05)
  for suite in (sys.argv[2:] or ('live_semantic.py','live_toolkits.py','live_range_selection.py','live_menu.py','live_detached_menu.py')):
   command=[sys.executable,str(root/'tests'/suite)];start=time.monotonic()
   with (out/(suite+'.log')).open('w') as log:
    try:code=subprocess.run(command,stdout=log,stderr=log,timeout=100).returncode
    except subprocess.TimeoutExpired:code='timeout'
   result={'suite':suite,'command':command,'returncode':code,'seconds':round(time.monotonic()-start,2)};results.append(result);print(json.dumps(result),flush=True)
 finally:
  wm.terminate();wm.wait(timeout=5)
  (out/'summary.json').write_text(json.dumps({'source_commit':source,'uid':os.getuid(),'display':os.environ['DISPLAY'],'cursor':'default enabled','suites':results},indent=2)+'\n')
