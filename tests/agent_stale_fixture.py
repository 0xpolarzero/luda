"""Owned visual-only board; every click has an independent harmless oracle."""
import json,sys
from pathlib import Path
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,Gdk
out=Path(sys.argv[1]);state={'selected':None,'commits':0,'clicks':[]}
window=Gtk.Window(title='Parcel Board');window.set_default_size(600,320)
canvas=Gtk.DrawingArea();canvas.get_accessible().set_name('Parcel board canvas');window.add(canvas)
canvas.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
def save():
 p=out/'board.tmp';p.write_text(json.dumps(state));p.replace(out/'board.json')
def draw(widget,ctx):
 ctx.set_source_rgb(.96,.97,.98);ctx.paint()
 def label(x,y,value):
  ctx.set_source_rgb(.1,.1,.1);ctx.set_font_size(20);ctx.move_to(x,y);ctx.show_text(value)
 label(25,40,'Choose a parcel label, then Commit')
 for i,(name,color) in enumerate([('Blue',(.4,.65,1)),('Amber',(1,.72,.2)),('Green',(.4,.85,.6))]):
  ctx.set_source_rgb(*color);ctx.rectangle(25+i*190,80,170,90);ctx.fill();label(45+i*190,130,name)
 ctx.set_source_rgb(.8,.82,.88);ctx.rectangle(380,235,180,55);ctx.fill();label(420,270,'Commit')
 label(25,210,'Selected: '+str(state['selected']))
 label(25,270,('Saved '+str(state['selected'])) if state['commits'] else 'Not saved')
def press(widget,event):
 target='background'
 for i,name in enumerate(('Blue','Amber','Green')):
  if 25+i*190<=event.x<195+i*190 and 80<=event.y<170:target=name;state['selected']=name
 if 380<=event.x<560 and 235<=event.y<290:
  target='Commit'
  if state['selected']:state['commits']+=1
 state['clicks'].append({'target':target,'x':event.x,'y':event.y});save();canvas.queue_draw()
canvas.connect('draw',draw);canvas.connect('button-press-event',press)
window.connect('destroy',Gtk.main_quit);window.show_all();save();Gtk.main()
