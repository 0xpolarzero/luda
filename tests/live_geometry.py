"""Independent geometry/pixel/pointer oracles on an explicitly isolated desktop."""
import base64
import io
import json
import os
import re
import subprocess
import time
from PIL import Image
from luda.common import DesktopError
from luda.desktop import Desktop

if os.environ.get('LUDA_ISOLATED_TEST_DISPLAY') != '1':
    raise SystemExit('Requires an explicitly isolated Xvfb/XFWM/D-Bus session.')
fixture = '''import gi,sys
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,Gdk
w=Gtk.Window(title='Luda geometry '+sys.argv[1]);w.set_default_size(431,277)
w.set_decorated(sys.argv[1]=='decorated')
style=Gtk.CssProvider();style.load_from_data(b'window {background-color: #123456;}')
Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(),style,Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
w.connect('destroy',Gtk.main_quit);w.show_all();Gtk.main()
'''
results=[]
d=Desktop()
def check_error(callback,code):
    try:callback()
    except DesktopError as exc:assert exc.code==code,(exc.code,code)
    else:raise AssertionError('Expected '+code)
def pointer():
    return {k:int(v) for k,v in re.findall(r'^(X|Y)=([0-9]+)$',subprocess.check_output(['xdotool','getmouselocation','--shell']).decode(),re.M)}
def independent_bounds(xid):
    text=subprocess.check_output(['xwininfo','-id',str(xid)]).decode()
    labels={'x':'Absolute upper-left X','y':'Absolute upper-left Y','width':'Width','height':'Height'}
    return {key:int(re.search(re.escape(label)+r':\s*(-?\d+)',text).group(1)) for key,label in labels.items()}
def snapshot(window,width):
    snap=d.observe(width)
    observed=next(v for v in snap['windows'] if v['window_id']==window['window_id'])
    assert observed['bounds']==independent_bounds(window['xid'])
    assert snap['coordinate_spaces']['bounds']=='native_x11_root_pixels'
    assert snap['coordinate_spaces']['image_bounds']=='returned_image_pixels'
    native=snap['desktop_size'];scaled=snap['image_size'];bounds=observed['bounds']
    columns=[i for i in range(scaled['width']) if bounds['x']<=i*native['width']//scaled['width']<bounds['x']+bounds['width']]
    rows=[i for i in range(scaled['height']) if bounds['y']<=i*native['height']//scaled['height']<bounds['y']+bounds['height']]
    expected=None if not columns or not rows else {'x':columns[0],'y':rows[0],'width':len(columns),'height':len(rows)}
    assert observed['image_bounds']==expected,(observed,expected)
    image=Image.open(io.BytesIO(base64.b64decode(snap['image_base64'])))
    assert image.size==(snap['image_size']['width'],snap['image_size']['height'])
    return snap,observed,image
try:
    for style in ('decorated','borderless'):
        app=subprocess.Popen(['/usr/bin/python3','-c',fixture,style],stdout=subprocess.DEVNULL)
        try:
            deadline=time.monotonic()+6
            while True:
                window=next((v for v in d.list_windows() if v['pid']==app.pid),None)
                if window:break
                assert time.monotonic()<deadline,'fixture did not appear'
                time.sleep(.04)
            with d.transaction():
                d.activate(window['window_id'])
                d.manage_window(window['window_id'],'move',x=80,y=100)
                for width in (1280,777,321):
                    snap,w,image=snapshot(window,width)
                    b=w['bounds'];iw,ih=image.size;nw,nh=snap['desktop_size']['width'],snap['desktop_size']['height']
                    x=(b['x']+b['width']//2)*iw/nw;y=(b['y']+b['height']//2)*ih/nh
                    assert image.getpixel((int(x),int(y)))==(18,52,86)
                    area=w['image_bounds']
                    ix=area['x']+area['width']//2;iy=area['y']+area['height']//2
                    d.hover(window['window_id'],snap['snapshot_id'],ix,iy)
                    assert pointer()=={'X':ix*nw//iw,'Y':iy*nh//ih}
                    d.hover(window['window_id'],snap['snapshot_id'],x,y)
                    assert pointer()=={'X':int(x*nw/iw),'Y':int(y*nh/ih)}
                    for a,c in ((iw,y),(x,ih),(-.1,y),(x,-.1)):
                        check_error(lambda:d.hover(window['window_id'],snap['snapshot_id'],a,c),'OUT_OF_BOUNDS')
                    results.append({'style':style,'returned_width':width,'pixel_and_pointer_oracles':True})
                if style=='borderless':assert w['bounds']==w['frame_bounds'],w
                if style=='decorated':
                    # Real RandR 1.5 monitor mutation without changing root
                    # dimensions, independently visible through xrandr.
                    monitor='luda-geometry-'+str(os.getpid())
                    subprocess.run(['xrandr','--setmonitor',monitor,'320/85x240/64+0+0','none'],check=True)
                    try:
                        assert monitor in subprocess.check_output(['xrandr','--listmonitors']).decode()
                        current=d.display().topology()
                        assert current['root']==snap['display_topology']['root']
                        assert current!=snap['display_topology']
                        check_error(lambda:d.hover(window['window_id'],snap['snapshot_id'],x,y),'STALE_OBSERVATION')
                        snap,w,image=snapshot(window,321)
                        d.hover(window['window_id'],snap['snapshot_id'],x,y)
                        results.append({'same_root_monitor_addition':'old pointer observation refused; fresh observation accepted'})
                    finally:subprocess.run(['xrandr','--delmonitor',monitor],check=True)
                    check_error(lambda:d.hover(window['window_id'],snap['snapshot_id'],x,y),'STALE_OBSERVATION')
                    snap,w,image=snapshot(window,321)
                old=snap['snapshot_id']
                d.manage_window(window['window_id'],'move',x=-100,y=100)
                check_error(lambda:d.hover(window['window_id'],old,x,y),'STALE_OBSERVATION')
                snap,w,image=snapshot(window,777)
                assert w['bounds']['x']<0,w
                x=20*image.width/snap['desktop_size']['width'];y=(w['bounds']['y']+30)*image.height/snap['desktop_size']['height']
                d.hover(window['window_id'],snap['snapshot_id'],x,y)
                assert pointer()['X']==20
                results.append({'style':style,'partially_offscreen_visible_region':True,'moved_snapshot_refused':True})
                d.manage_window(window['window_id'],'fullscreen')
                snap,w,image=snapshot(window,2560)
                assert w['bounds']=={'x':0,'y':0,**snap['desktop_size']},w
                d.hover(window['window_id'],snap['snapshot_id'],image.width-1,image.height-1)
                assert pointer()=={'X':image.width-1,'Y':image.height-1}
                results.append({'style':style,'fullscreen_last_native_pixel':True})
        finally:
            app.terminate();app.wait(timeout=5)
finally:d.close()
print(json.dumps(results,indent=2))
