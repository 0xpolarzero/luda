"""Unseen-to-agent form; the harness independently reads committed values."""
import json
from pathlib import Path
import sys
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk

output=Path(sys.argv[1])
if len(sys.argv)>2 and sys.argv[2]=='canvas':
    import cairo
    from gi.repository import Gdk
    window=Gtk.Window(title='Luda visual task');window.set_default_size(640,500)
    canvas=Gtk.DrawingArea();canvas.get_accessible().set_name('Visual board')
    canvas.add_events(Gdk.EventMask.BUTTON_PRESS_MASK);window.add(canvas)
    state={'color':'Blue','cell':None,'menu':False,'saved':False}
    def draw(widget,ctx):
        ctx.set_source_rgb(.96,.97,.98);ctx.paint()
        def label(x,y,text,size=18):
            ctx.set_source_rgb(.08,.1,.15);ctx.set_font_size(size);ctx.move_to(x,y);ctx.show_text(text)
        label(25,35,'Dispatch board',24)
        ctx.set_source_rgb(.8,.84,.9);ctx.rectangle(25,55,180,45);ctx.fill()
        label(40,84,'Palette: '+state['color'])
        for row in range(3):
            for col in range(3):
                x,y=95+col*125,135+row*90
                ctx.set_source_rgb(1,1,1);ctx.rectangle(x,y,115,80);ctx.fill_preserve();ctx.set_source_rgb(.35,.4,.5);ctx.stroke()
                cell=chr(65+col)+str(row+1);label(x+10,y+25,cell)
                if state['cell']==cell:
                    ctx.set_source_rgb(*({'Blue':(.1,.4,.9),'Amber':(1,.65,.05),'Green':(.1,.6,.3)}[state['color']]))
                    ctx.arc(x+58,y+48,18,0,6.2832);ctx.fill()
        ctx.set_source_rgb(.8,.84,.9);ctx.rectangle(440,420,150,45);ctx.fill();label(470,450,'Commit')
        label(25,450,('Saved '+state['cell']+' '+state['color']) if state['saved'] else 'Not saved')
        if state['menu']:
            for i,color in enumerate(('Blue','Amber','Green')):
                ctx.set_source_rgb(.9,.92,.95);ctx.rectangle(25,105+i*42,180,42);ctx.fill_preserve();ctx.set_source_rgb(.4,.45,.5);ctx.stroke();label(40,132+i*42,color)
    def press(widget,event):
        x,y=event.x,event.y
        if state['menu']:
            if 25<=x<=205 and 105<=y<231:state['color']=('Blue','Amber','Green')[int((y-105)//42)];state['saved']=False
            state['menu']=False
        elif 25<=x<=205 and 55<=y<=100:state['menu']=True
        elif 95<=x<470 and 135<=y<405:
            col,row=int((x-95)//125),int((y-135)//90)
            if (x-95)%125<115 and (y-135)%90<80:state['cell']=chr(65+col)+str(row+1);state['saved']=False
        elif 440<=x<=590 and 420<=y<=465 and state['cell']:
            state['saved']=True;output.write_text(json.dumps({'color':state['color'],'cell':state['cell'],'saved':True}))
        canvas.queue_draw()
    canvas.connect('draw',draw);canvas.connect('button-press-event',press)
    window.connect('destroy',Gtk.main_quit);window.show_all();Gtk.main();raise SystemExit
window=Gtk.Window(title='Luda agent task');window.set_default_size(560,440)
box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12);box.set_border_width(20);window.add(box)
box.pack_start(Gtk.Label(label='Delivery preferences'),False,False,0)
text=Gtk.TextView();text.get_accessible().set_name('Delivery note');box.pack_start(text,True,True,0)
updates=Gtk.CheckButton(label='Send updates');box.pack_start(updates,False,False,0)
standard=Gtk.RadioButton.new_with_label_from_widget(None,'Standard delivery')
express=Gtk.RadioButton.new_with_label_from_widget(standard,'Express delivery')
box.pack_start(standard,False,False,0);box.pack_start(express,False,False,0)
status=Gtk.Label(label='Not saved');status.get_accessible().set_name('Save status');box.pack_start(status,False,False,0)
button=Gtk.Button(label='Save preferences');box.pack_start(button,False,False,0)
def save(*unused):
    buffer=text.get_buffer();start,end=buffer.get_bounds()
    temporary=output.with_suffix('.tmp')
    temporary.write_text(json.dumps({'note':buffer.get_text(start,end,True),'updates':updates.get_active(),'express':express.get_active()},ensure_ascii=False))
    temporary.replace(output);status.set_text('Preferences saved')
button.connect('clicked',save)
window.connect('destroy',Gtk.main_quit);window.show_all();Gtk.main()
