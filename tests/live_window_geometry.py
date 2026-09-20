"""Private ordinary-UID Xvfb/D-Bus only; independently measure GTK WM constraints."""
import json
import os
from pathlib import Path
import re
import subprocess
import time
from luda.desktop import Desktop

FIXTURE='''import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,Gdk
w=Gtk.Window(title='Luda owned geometry constraints')
w.set_default_size(420,260)
g=Gdk.Geometry();g.min_width=300;g.min_height=180;g.base_width=300;g.base_height=180;g.width_inc=40;g.height_inc=20
w.set_geometry_hints(None,g,Gdk.WindowHints.MIN_SIZE|Gdk.WindowHints.BASE_SIZE|Gdk.WindowHints.RESIZE_INC)
w.connect('destroy',Gtk.main_quit);w.show_all();Gtk.main()
'''

def oracle(xid):
    raw=subprocess.check_output(['xwininfo','-id',str(xid)],text=True)
    def number(label):return int(re.search(r'^\s*'+re.escape(label)+r':\s*(-?\d+)',raw,re.M)[1])
    client={key:number(label) for key,label in [('x','Absolute upper-left X'),('y','Absolute upper-left Y'),('width','Width'),('height','Height')]}
    props=subprocess.check_output(['xprop','-id',str(xid),'_NET_FRAME_EXTENTS','_NET_WM_STATE','WM_NORMAL_HINTS'],text=True)
    extents=re.search(r'_NET_FRAME_EXTENTS\(CARDINAL\) = (\d+), (\d+), (\d+), (\d+)',props)
    left,right,top,bottom=map(int,extents.groups())
    frame=dict(x=client['x']-left,y=client['y']-top,width=client['width']+left+right,height=client['height']+top+bottom)
    return {'client_bounds':client,'frame_bounds':frame,'properties':props}


def main():
    assert os.geteuid()!=0 and os.environ.get('LUDA_ISOLATED_TEST_DISPLAY')=='1'
    output=Path(os.environ['LUDA_GEOMETRY_OUTPUT']);output.mkdir(parents=True,exist_ok=False)
    wm=subprocess.Popen(['xfwm4','--compositor=off'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    app=None;driver=None;records=[]
    try:
        time.sleep(.4)
        app=subprocess.Popen(['/usr/bin/python3','-c',FIXTURE])
        driver=Desktop();deadline=time.monotonic()+8
        while True:
            window=next((w for w in driver.list_windows() if w['pid']==app.pid),None)
            if window:break
            if time.monotonic()>deadline:raise AssertionError('owned fixture missing')
            time.sleep(.05)
        with driver.transaction():
            for action,args in [('move',dict(x=100,y=120)),('resize',dict(width=100,height=100)),('resize',dict(width=333,height=197)),('resize',dict(width=420,height=260)),('maximize',{}),('restore',{})]:
                result=driver.manage_window(window['window_id'],action,**args)
                actual=oracle(window['xid']);observed=result['observed_geometry']
                records.append({'action':action,'result':result,'independent_oracle':actual})
                (output/'observations.json').write_text(json.dumps(records,indent=2)+'\n')
                assert observed['client_bounds']==actual['client_bounds'],(result,actual)
                assert observed['frame_bounds']==actual['frame_bounds'],(result,actual)
                for key,atom in [('maximized_horizontal','MAXIMIZED_HORZ'),('maximized_vertical','MAXIMIZED_VERT'),('fullscreen','FULLSCREEN'),('hidden','HIDDEN')]:
                    assert observed['wm_state'][key]==('_NET_WM_STATE_'+atom in actual['properties'])
                if action=='resize':
                    assert actual['client_bounds']['width']>=300 and actual['client_bounds']['height']>=180
                    assert 'resize increment: 40 by 20' in actual['properties']
                    if args['width']==100:
                        assert result['effect']=='dispatched' and observed['request_match']=='nonmatching'
                    elif args['width']==333:
                        matched=all(actual['client_bounds'][key]==value for key,value in args.items())
                        assert observed['request_match']==('matched' if matched else 'nonmatching')
                    else:before_maximize=actual
                if action=='restore':assert actual['client_bounds']==before_maximize['client_bounds']
        (output/'results.json').write_text(json.dumps({'checks':len(records),'results':records},indent=2)+'\n')
        print(json.dumps({'passed':len(records),'scope':'GTK3/XFWM private Xvfb minimum/increment resize and maximize/restore'}))
    finally:
        if driver:driver.close()
        for process in (app,wm):
            if process:
                process.terminate()
                try:process.wait(timeout=3)
                except subprocess.TimeoutExpired:process.kill();process.wait()

if __name__=='__main__':main()
