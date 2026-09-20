"""Read-only Luda metadata against deliberately reconfigured owned X servers."""
import argparse
import json
import os
from pathlib import Path
import select
import shutil
import subprocess
import sys
import platform
import uuid
import tempfile
from luda.common import DesktopError,environment_scope,stop_process
from luda.x11 import X11

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'scripts'))
from qualify import source_fingerprint
from qualification_matrix import cleanup_owned,TOKEN_KEY
CONFIG='''Section "ServerFlags"
 Option "AutoAddDevices" "false"
 Option "AutoEnableDevices" "false"
 Option "DontVTSwitch" "true"
EndSection
Section "Device"
 Identifier "Dummy"
 Driver "dummy"
 VideoRam 256000
EndSection
Section "Monitor"
 Identifier "Monitor"
 HorizSync 5.0 - 1000.0
 VertRefresh 5.0 - 200.0
 Modeline "1280x720" 74.50 1280 1344 1472 1664 720 723 728 748 -hsync +vsync
EndSection
Section "Screen"
 Identifier "Screen"
 Device "Dummy"
 Monitor "Monitor"
 DefaultDepth 24
 SubSection "Display"
  Depth 24
  Modes "1280x720"
  Virtual 2560 1440
 EndSubSection
EndSection
'''


def probe(kind,out):
    with tempfile.TemporaryDirectory(prefix='luda-randr-'+kind+'-') as directory:
        base=Path(directory);reader,writer=os.pipe()
        command=['Xvfb','-screen','0','1280x720x24']
        if kind=='no-randr':command.extend(['-extension','RANDR'])
        elif kind=='dummy':
            config=base/'xorg.conf';config.write_text(CONFIG)
            command=['/usr/lib/xorg/Xorg','-config',str(config),'-logfile',str(base/'xorg.log')]
        elif kind=='kasm':
            command=['Xvnc','-geometry','1280x720','-depth','24','-noWebsocket','-rfbunixpath',str(base/'vnc.sock'),'-rfbport','-1','-SecurityTypes','None','-localhost','-publicIP','127.0.0.1']
        command.extend(['-displayfd',str(writer),'-noreset','-nolisten','tcp','-ac'])
        token=uuid.uuid4().hex
        result={'backend':kind,'command':command,'checks':[],'capabilities':[]}
        with (out/(kind+'-server.log')).open('w') as log:
            child=subprocess.Popen(command,pass_fds=(writer,),stdout=log,stderr=log)
            os.close(writer)
            try:
                assert select.select([reader],[],[],8)[0],'Owned server startup timed out'
                number=os.read(reader,32).decode().strip();assert number.isdigit(),('Server did not provide a display',child.poll())
                env=dict(os.environ,DISPLAY=':'+number,**{TOKEN_KEY:token});env.pop('XAUTHORITY',None)
                def xr(*arguments):return subprocess.run(['xrandr',*arguments],env=env,text=True,capture_output=True,timeout=4)
                with environment_scope(env):
                    display=X11()
                    if kind=='no-randr':
                        extensions=subprocess.check_output(['xdpyinfo','-queryExtensions'],env=env,text=True,timeout=3)
                        assert 'RANDR' not in extensions
                        try:display.topology()
                        except DesktopError as error:
                            assert error.code=='TOPOLOGY_UNAVAILABLE',error.code
                            result['checks'].append({'case':'actual-missing-extension-refused','code':error.code})
                        else:raise AssertionError('Missing RandR silently accepted')
                        semantic_env=dict(env,NO_AT_BRIDGE='0',GSETTINGS_BACKEND='memory',LUDA_ISOLATED_TEST_DISPLAY='1')
                        for key in ('XDG_CONFIG_HOME','XDG_CACHE_HOME','XDG_DATA_HOME','XDG_RUNTIME_DIR'):
                            path=base/key;path.mkdir(mode=0o700);semantic_env[key]=str(path)
                        semantic_env['XDG_CONFIG_DIRS']=semantic_env['XDG_CONFIG_HOME']
                        for key in ('DBUS_SESSION_BUS_ADDRESS','AT_SPI_BUS_ADDRESS','SESSION_MANAGER'):
                            semantic_env.pop(key,None)
                        semantics=subprocess.run(['dbus-run-session','--',sys.executable,str(ROOT/'tests/randr_no_extension_fixture.py'),str(base)],env=semantic_env,capture_output=True,text=True,timeout=20)
                        (out/'no-randr-semantics.log').write_text(semantics.stdout+semantics.stderr)
                        assert semantics.returncode==0,semantics.stderr
                        result['checks'].append({'case':'semantic-tools-survive-missing-randr','evidence':json.loads((base/'semantic-result.json').read_text())})
                        return result
                    baseline=display.topology();result['baseline']=baseline
                    query=xr('--query');assert query.returncode==0;result['query']=query.stdout
                    result['checks'].append({'case':'native-topology-readable','version':baseline['randr']['version']})
                    output='DUMMY0' if kind=='dummy' else next(line.split()[0] for line in query.stdout.splitlines() if ' connected' in line)
                    if kind=='dummy':
                        for arguments in [('--addmode','DUMMY1','1280x720'),('--output','DUMMY1','--mode','1280x720','--right-of','DUMMY0')]:
                            command_result=xr(*arguments);assert command_result.returncode==0,command_result.stderr
                        before=display.topology();active=[row for row in before['randr']['crtcs'] if row['mode']]
                        assert len(active)==2 and sorted(row['x'] for row in active)==[0,1280]
                        swapped=xr('--output','DUMMY0','--pos','1280x0','--output','DUMMY1','--pos','0x0');assert swapped.returncode==0,swapped.stderr
                        after=display.topology();assert before['root']==after['root'] and before!=after
                        assert '1280x720+1280+0' in xr('--query').stdout
                        result['checks'].append({'case':'two-real-crtcs-same-root-layout-swap','root':after['root'],'before':active,'after':[row for row in after['randr']['crtcs'] if row['mode']]})
                    for name,arguments in [('rotation',('--rotate','left')),('transform',('--transform','0.75,0,0,0,0.75,0,0,0,1')),('panning',('--panning','1400x800'))]:
                        # xrandr can disable a CRTC before a rejected transform.
                        # Restore the owned baseline mode between independent probes.
                        restored=xr('--output',output,'--mode','1280x720','--pos','0x0')
                        assert restored.returncode==0,restored.stderr
                        before=display.topology()
                        assert any(c['mode'] for c in before['randr']['crtcs'])
                        attempt=xr('--output',output,*arguments);after=display.topology()
                        row={'capability':name,'status':'supported' if attempt.returncode==0 else 'driver_refused','returncode':attempt.returncode,'stderr':attempt.stderr,'metadata_changed':before!=after}
                        if attempt.returncode==0:
                            assert before!=after,(name,'Configuration accepted without detectable metadata change')
                            if name=='panning':assert any(c['panning'] and c['panning']['width']==1400 for c in after['randr']['crtcs'])
                        result['capabilities'].append(row)
                    result['final']=display.topology()
                    return result
            finally:
                os.close(reader);stop_process(child)
                result['cleanup']=cleanup_owned(token)
                assert not result['cleanup']['survivors'],result['cleanup']
                if (base/'xorg.log').exists():shutil.copyfile(base/'xorg.log',out/(kind+'-xorg.log'))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backends',nargs='+',choices=['xvfb','kasm','dummy','no-randr'],default=['xvfb','kasm','dummy','no-randr'])
    args=parser.parse_args()
    if os.getuid()==0:parser.error('Use an ordinary account; every display is created privately')
    out=ROOT/'artifacts/randr-backends';out.mkdir(parents=True,exist_ok=True)
    rows=[];source_before=source_fingerprint(ROOT)
    try:
        for backend in args.backends:
            row=probe(backend,out);rows.append(row)
            print(json.dumps({'backend':backend,'checks':len(row['checks']),'capabilities':row['capabilities']}),flush=True)
    finally:
        source_after=source_fingerprint(ROOT)
        packages=subprocess.run(['dpkg-query','-W','libxrandr2','libxrandr-dev','xserver-xorg-video-dummy','xserver-xorg-core','xvfb'],text=True,capture_output=True,timeout=3)
        (out/'results.json').write_text(json.dumps({'uid':os.getuid(),'architecture':platform.machine(),'packages':packages.stdout.splitlines(),'backends':rows,'source_before':source_before,'source_after':source_after,'source_unchanged':source_before==source_after},indent=2)+'\n')
    assert source_before==source_after,'Qualification sources changed during the run'

if __name__=='__main__':main()
