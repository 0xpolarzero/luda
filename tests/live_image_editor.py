"""Private ordinary-user GIMP canvas qualification through public stdio MCP."""
import asyncio,base64,hashlib,json,os,signal,subprocess,sys,tempfile,time
from pathlib import Path
from PIL import Image,ImageDraw,UnidentifiedImageError
from mcp import ClientSession,StdioServerParameters
from mcp.client.stdio import stdio_client
ROOT=Path(__file__).resolve().parents[1]
ARTIFACTS=Path(os.environ.get('LUDA_IMAGE_ARTIFACTS',str(ROOT/'artifacts/image-editor')))

async def child():
 ARTIFACTS.mkdir(parents=True,exist_ok=True)
 with tempfile.TemporaryDirectory(prefix='luda-image-oracle-') as directory:
  base=Path(directory);source=base/'authored.png'
  image=Image.new('RGB',(640,480),'white');draw=ImageDraw.Draw(image)
  draw.rectangle((0,0,19,479),fill=(255,0,255));draw.rectangle((620,0,639,479),fill=(0,255,255));image.save(source);source_hash=hashlib.sha256(source.read_bytes()).hexdigest()
  (ARTIFACTS/'authored.png').write_bytes(source.read_bytes())
  wm=subprocess.Popen(['xfwm4','--compositor=off'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL);app=None
  try:
   end=time.monotonic()+5
   while subprocess.run(['wmctrl','-m'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL).returncode:
    assert time.monotonic()<end;await asyncio.sleep(.05)
   log=(ARTIFACTS/'gimp.log').open('w')
   app=subprocess.Popen(['gimp','--no-splash','--new-instance',str(source)],stdout=log,stderr=log)
   async with stdio_client(StdioServerParameters(command=sys.executable,args=['-m','luda.server'],env=dict(os.environ))) as streams:
    async with ClientSession(*streams) as session:
     await session.initialize();trace=[]
     async def call(name,allow_error=False,**args):
      result=await session.call_tool(name,args)
      value=json.loads(next(c.text for c in result.content if c.type=='text'))
      trace.append({'name':name,'arguments':args,'result':value})
      (ARTIFACTS/'trace.json').write_text(json.dumps(trace,indent=2))
      assert allow_error or not result.isError,(name,value)
      return value,result
     owner=None
     for _ in range(200):
      windows,_=await call('desktop_windows')
      owner=next((w for w in windows['windows'] if w['pid']==app.pid and 'authored' in w['title']),None)
      if owner:break
      await asyncio.sleep(.1)
     assert owner;wid=owner['window_id']
     await call('desktop_activate',window_id=wid)
     await call('desktop_window',window_id=wid,action='maximize')
     await asyncio.sleep(.5)
     async def observe(label):
      snap,response=await call('desktop_observe')
      (ARTIFACTS/(label+'.png')).write_bytes(base64.b64decode(next(c.data for c in response.content if c.type=='image')))
      return snap
     async def key(chord):return await call('desktop_press_keys',window_id=wid,chord=chord)
     accessibility,_=await call('desktop_inspect',window_id=wid,limit=200,allow_error=True)
     assert accessibility.get('code')=='ACCESSIBILITY_UNAVAILABLE',accessibility
     snap=await observe('initial')
     assert snap['image_size']==snap['desktop_size']=={'width':1200,'height':900}
     # Locate the authored magenta rail in the returned screenshot, excluding
     # the miniature thumbnail by requiring a full-height contiguous rail.
     pixels=Image.open(ARTIFACTS/'initial.png').convert('RGB')
     columns=[]
     for x in range(pixels.width):
      ys=[y for y in range(120,pixels.height-40) if pixels.getpixel((x,y))==(255,0,255)]
      if len(ys)>=470:columns.append((x,min(ys),max(ys)))
     assert columns
     ox,oy=columns[0][0]-1,columns[0][1]-1
     assert columns[-1][0]-ox==19 and columns[0][2]-oy==478
     await key('d');await key('n')
     snap=await observe('pencil')
     await call('desktop_drag',window_id=wid,snapshot_id=snap['snapshot_id'],x=ox+100,y=oy+100,end_x=ox+400,end_y=oy+100)
     await key('r');snap=await observe('drawn')
     await call('desktop_drag',window_id=wid,snapshot_id=snap['snapshot_id'],x=ox+100,y=oy+220,end_x=ox+220,end_y=oy+300)
     await key('ctrl+comma');await key('ctrl+shift+a')
     await observe('selected-fill')
     await key('plus');await key('plus');snap=await observe('zoomed')
     await call('desktop_scroll',window_id=wid,snapshot_id=snap['snapshot_id'],x=600,y=500,direction='down',ticks=3)
     await observe('scrolled')
     def rectangle_rows(label):
      screenshot=Image.open(ARTIFACTS/(label+'.png')).convert('RGB')
      return [y for y in range(250,800) if all(screenshot.getpixel((x,y))==(0,0,0) for x in range(300,450))]
     before,after=rectangle_rows('zoomed'),rectangle_rows('scrolled')
     assert len(before)==len(after)==160 and min(before)-min(after)>20,(before[:1],after[:1])
     await key('1');await key('ctrl+shift+e');await asyncio.sleep(.4)
     await observe('export-dialog')
     windows,_=await call('desktop_windows')
     dialog=next(w for w in windows['windows'] if w['pid']==app.pid and w['title']=='Export Image')
     dialog_id=dialog['window_id']
     await call('desktop_press_keys',window_id=dialog_id,chord='ctrl+a')
     await call('desktop_paste',window_id=dialog_id,text=str(base/'exported.png'))
     await observe('export-path')
     await call('desktop_press_keys',window_id=dialog_id,chord='Return')
     await asyncio.sleep(.4);snap=await observe('png-options')
     windows,_=await call('desktop_windows')
     options=next(w for w in windows['windows'] if w['title']=='Export Image as PNG' and w['active'])
     bounds=next(w['image_bounds'] for w in snap['windows'] if w['window_id']==options['window_id'])
     # This fixed-version PNG dialog's observed Export button is bottom-right.
     await call('desktop_click',window_id=options['window_id'],snapshot_id=snap['snapshot_id'],x=bounds['x']+bounds['width']-55,y=bounds['y']+bounds['height']-28)
     output=base/'exported.png';end=time.monotonic()+8
     while True:
      try:
       with Image.open(output) as saved:exported=saved.convert('RGB')
       break
      except (FileNotFoundError,UnidentifiedImageError,OSError):
       assert time.monotonic()<end,'PNG export did not finish';await asyncio.sleep(.05)
     assert exported.size==(640,480)
     assert hashlib.sha256(source.read_bytes()).hexdigest()==source_hash
     black=0;changed=0
     for y in range(480):
      for x in range(640):
       actual=exported.getpixel((x,y));original=image.getpixel((x,y))
       stroke=74<=x<=426 and 74<=y<=126;selection=100<=x<220 and 220<=y<300
       if selection:assert actual==(0,0,0),(x,y,actual)
       if not(stroke or selection):assert actual==original,(x,y,actual,original)
       if actual!=original:changed+=1
       if actual==(0,0,0):black+=1
     for point in ((100,100),(250,100),(400,100)):
      assert exported.getpixel(point)==(0,0,0)
     assert changed==black and black>20000
     await observe('exported')
     (ARTIFACTS/'exported.png').write_bytes(output.read_bytes())
     result={'suite':'gimp-image-editor','uid':os.getuid(),'version':subprocess.check_output(['gimp','--version'],text=True).strip(),
       'package':subprocess.check_output(['dpkg-query','-W','-f=${Version}','gimp'],text=True),
       'cases':['screenshot-only-GTK2-observation','native-pencil-drag-exported-pixels','rectangle-selection-constrained-fill','zoomed-canvas-wheel-scroll','native-PNG-export-dialogs-independent-file-oracle'],
       'accessibility':accessibility['code'],'passed':5,'scroll_delta_pixels':min(before)-min(after),'export_size':list(exported.size),'black_pixels':black,'changed_pixels':changed,
       'source_sha256':source_hash,'export_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
       'limits':['GIMP 2.10 fixed theme, 1200x900 X11 and 100 percent initial zoom; not all image editor features.','Screenshot-only observed GTK2 backend; no claim of semantic canvas support.','Input results dispatched; independent PNG pixels establish application effects.']}
     (ARTIFACTS/'results.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
  finally:
   if app and app.poll() is None:app.terminate();app.wait(timeout=5)
   if wm.poll() is None:wm.terminate();wm.wait(timeout=3)

def main():
 if os.getuid()==0:raise SystemExit('Run as ordinary desktop account; uses a private Xvfb session.')
 if '--child' in sys.argv:return asyncio.run(child())
 with tempfile.TemporaryDirectory(prefix='luda-private-image-') as directory:
  env=dict(os.environ);base=Path(directory)
  env.setdefault('LUDA_IMAGE_ARTIFACTS',str(ROOT/'artifacts/image-editor'/('run-'+str(time.time_ns()))))
  for key in ('XDG_CONFIG_HOME','XDG_DATA_HOME','XDG_CACHE_HOME','XDG_RUNTIME_DIR'):
   path=base/key;path.mkdir(mode=0o700);env[key]=str(path)
  env.update(XDG_CONFIG_DIRS=env['XDG_CONFIG_HOME'],GIMP2_DIRECTORY=str(base/'gimp'),LANG='C.UTF-8',LC_ALL='C.UTF-8')
  process=subprocess.Popen(['xvfb-run','-a','-s','-screen 0 1200x900x24','dbus-run-session','--',sys.executable,__file__,'--child'],env=env,start_new_session=True)
  try:code=process.wait(timeout=100)
  finally:
   try:os.killpg(process.pid,signal.SIGTERM)
   except ProcessLookupError:pass
   try:process.wait(timeout=3)
   except subprocess.TimeoutExpired:pass
   try:os.killpg(process.pid,signal.SIGKILL)
   except ProcessLookupError:pass
   process.wait(timeout=3)
 raise SystemExit(code)
if __name__=='__main__':main()
