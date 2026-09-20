"""Explicit reconnecting AT-SPI provider over a real persistent GTK window.

This fixture models an application's reconnect policy; ordinary GTK's bridge is
intentionally disabled and is not claimed to support this lifecycle.
"""
import json
import os
from pathlib import Path
import sys
import gi
gi.require_version('Gtk','3.0');gi.require_version('Atspi','2.0')
from gi.repository import Gtk,Gio,GLib,Atspi

OUT=Path(sys.argv[1]);OUT.mkdir(exist_ok=True)
ROOT='/org/a11y/atspi/accessible/root';TOP='/fixture/window';BUTTON='/fixture/button'
window=Gtk.Window(title='Luda Bus Generation Fixture');window.set_default_size(350,130)
button=Gtk.Button(label='Generation action');window.add(button);window.show_all()
state={'actions':0,'generation':0};connection=None

def save():
 (OUT/'state.tmp').write_text(json.dumps(state));(OUT/'state.tmp').replace(OUT/'state.json')
def clicked(*_):state['actions']+=1;save()
button.connect('clicked',clicked)

def interface(name,properties,methods):
 parts=['<node><interface name="org.a11y.atspi.'+name+'">']
 for prop,kind in properties:parts.append(f'<property name="{prop}" type="{kind}" access="read"/>')
 for method,inputs,outputs in methods:
  parts.append(f'<method name="{method}">')
  for direction,kinds in [('in',inputs),('out',outputs)]:
   parts.extend(f'<arg type="{kind}" direction="{direction}"/>' for kind in kinds)
  parts.append('</method>')
 return Gio.DBusNodeInfo.new_for_xml(''.join(parts)+'</interface></node>').interfaces[0]
INFOS={
 'Accessible':interface('Accessible',[('Name','s'),('Description','s'),('Parent','(so)'),('ChildCount','i')],[('GetChildAtIndex',['i'],['(so)']),('GetChildren',[],['a(so)']),('GetIndexInParent',[],['i']),('GetRole',[],['u']),('GetRoleName',[],['s']),('GetLocalizedRoleName',[],['s']),('GetState',[],['au']),('GetAttributes',[],['a{ss}']),('GetApplication',[],['(so)']),('GetInterfaces',[],['as'])]),
 'Application':interface('Application',[('ToolkitName','s'),('Version','s'),('AtspiVersion','s'),('Id','i')],[]),
 'Component':interface('Component',[],[('GetExtents',['u'],['(iiii)']),('GrabFocus',[],['b'])]),
 'Action':interface('Action',[('NActions','i')],[('GetName',['i'],['s']),('GetDescription',['i'],['s']),('GetLocalizedName',['i'],['s']),('GetKeyBinding',['i'],['s']),('DoAction',['i'],['b']),('GetActions',[],['a(sss)'])])}

def children(path):return [TOP] if path==ROOT else [BUTTON] if path==TOP else []
def interfaces(path):return ['Accessible','Application'] if path==ROOT else ['Accessible','Component']+(['Action'] if path==BUTTON else [])
def ref(path):return (connection.get_unique_name(),path)
def prop(conn,sender,path,iface,name):
 values={'Name':GLib.Variant('s',{ROOT:'Explicit reconnect provider',TOP:'Luda Bus Generation Fixture',BUTTON:'Generation action'}[path]),'Description':GLib.Variant('s',''),'Parent':GLib.Variant('(so)',ref(ROOT if path==TOP else TOP if path==BUTTON else '/org/a11y/atspi/null')),'ChildCount':GLib.Variant('i',len(children(path))),'ToolkitName':GLib.Variant('s','LudaFixture'),'Version':GLib.Variant('s','1'),'AtspiVersion':GLib.Variant('s','2.1'),'Id':GLib.Variant('i',1),'NActions':GLib.Variant('i',1)}
 return values.get(name)
def method(conn,sender,path,iface,name,args,invocation):
 try:
  role=Atspi.Role.APPLICATION if path==ROOT else Atspi.Role.FRAME if path==TOP else Atspi.Role.PUSH_BUTTON
  if name=='GetChildren':result=GLib.Variant('(a(so))',([ref(p) for p in children(path)],))
  elif name=='GetChildAtIndex':result=GLib.Variant('((so))',(ref(children(path)[args.unpack()[0]]),))
  elif name=='GetIndexInParent':result=GLib.Variant('(i)',(0,))
  elif name=='GetRole':result=GLib.Variant('(u)',(int(role),))
  elif name in ('GetRoleName','GetLocalizedRoleName'):result=GLib.Variant('(s)',({ROOT:'application',TOP:'frame',BUTTON:'push button'}[path],))
  elif name=='GetState':
   mask=sum(1<<int(s) for s in (Atspi.StateType.ENABLED,Atspi.StateType.SENSITIVE,Atspi.StateType.SHOWING,Atspi.StateType.VISIBLE))
   result=GLib.Variant('(au)',([mask&0xffffffff,mask>>32],))
  elif name=='GetAttributes':result=GLib.Variant('(a{ss})',({},))
  elif name=='GetApplication':result=GLib.Variant('((so))',(ref(ROOT),))
  elif name=='GetInterfaces':result=GLib.Variant('(as)',(['org.a11y.atspi.'+x for x in interfaces(path)],))
  elif name=='GetExtents':
   _,x,y=window.get_window().get_origin();width,height=window.get_size();result=GLib.Variant('((iiii))',((x,y,width,height),))
  elif name=='GrabFocus':button.grab_focus();result=GLib.Variant('(b)',(True,))
  elif name in ('GetName','GetLocalizedName'):result=GLib.Variant('(s)',('click',))
  elif name in ('GetDescription','GetKeyBinding'):result=GLib.Variant('(s)',('',))
  elif name=='GetActions':result=GLib.Variant('(a(sss))',([('click','','')],))
  elif name=='DoAction':button.clicked();result=GLib.Variant('(b)',(True,))
  else:raise ValueError('Unknown fixture method')
  invocation.return_value(result)
 except Exception:invocation.return_dbus_error('org.luda.FixtureError','Fixture method failed')
def attach(address,wanted=None):
 global connection
 flags=Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT|Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION
 if wanted:
  # Allocate only this private replacement bus's earlier unique connection names.
  for _ in range(32):
   candidate=Gio.DBusConnection.new_for_address_sync(address,flags,None,None)
   if candidate.get_unique_name()==wanted:connection=candidate;break
   candidate.close_sync(None)
  else:raise RuntimeError('Cannot reproduce bounded connection name')
 else:connection=Gio.DBusConnection.new_for_address_sync(address,flags,None,None)
 connection.set_exit_on_close(False)
 for path in (ROOT,TOP,BUTTON):
  for name in interfaces(path):connection.register_object(path,INFOS[name],method,prop,None)
 connection.call('org.a11y.atspi.Registry',ROOT,'org.a11y.atspi.Socket','Embed',GLib.Variant('((so))',(ref(ROOT),)),None,Gio.DBusCallFlags.NONE,2000,None,None,None)
 state.update(generation=state['generation']+1,provider=connection.get_unique_name(),guid=connection.get_guid());save()
def tick():
 command=OUT/'attach.json'
 if command.exists():
  request=json.loads(command.read_text());command.unlink()
  try:attach(**request)
  except Exception as e:state['error']=type(e).__name__;save()
 return True
GLib.timeout_add(30,tick);save();Gtk.main()
