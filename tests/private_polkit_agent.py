"""Real authority protocol, cancel-only custom GTK agent; never accepts credentials."""
import gi,json,os,subprocess,sys
from pathlib import Path
gi.require_version('Gtk','3.0')
from gi.repository import Gio,GLib,Gtk
out=Path(sys.argv[1]);state={'agent_pid':os.getpid(),'uid':os.getuid(),'begin_authentication':0,'gui_cancel':0,'caller_exit':None,'credentials_entered':0,'authorization_responses':0}
def save():
 p=out/'state.tmp';p.write_text(json.dumps(state));p.replace(out/'state.json')
bus=Gio.bus_get_sync(Gio.BusType.SYSTEM,None)
owner=bus.call_sync('org.freedesktop.DBus','/org/freedesktop/DBus','org.freedesktop.DBus','GetNameOwner',GLib.Variant('(s)',('org.freedesktop.PolicyKit1',)),None,Gio.DBusCallFlags.NONE,3000,None).unpack()[0]
pid=bus.call_sync('org.freedesktop.DBus','/org/freedesktop/DBus','org.freedesktop.DBus','GetConnectionUnixProcessID',GLib.Variant('(s)',(owner,)),None,Gio.DBusCallFlags.NONE,3000,None).unpack()[0]
state['authority_owner']=owner;state['authority_pid']=pid
assert pid==int(os.environ['LUDA_TEST_AUTHORITY_PID'])
xml='''<node><interface name="org.freedesktop.PolicyKit1.AuthenticationAgent"><method name="BeginAuthentication"><arg type="s" direction="in"/><arg type="s" direction="in"/><arg type="s" direction="in"/><arg type="a{ss}" direction="in"/><arg type="s" direction="in"/><arg type="a(sa{sv})" direction="in"/></method><method name="CancelAuthentication"><arg type="s" direction="in"/></method></interface></node>'''
window=None
pending=None
def method(connection,sender,path,interface,name,parameters,invocation):
 global window,pending
 if sender!=owner:invocation.return_dbus_error('org.freedesktop.PolicyKit1.Error.Failed','Wrong authority');return
 if name=='CancelAuthentication':
  if pending:pending.return_dbus_error('org.freedesktop.PolicyKit1.Error.Cancelled','Cancelled');pending=None
  if window:window.destroy()
  invocation.return_value(None);return
 action,message,icon,details,cookie,identities=parameters.unpack()
 if (action!='org.freedesktop.policykit.exec' or details.get('polkit.caller-pid')!=str(caller.pid)
     or details.get('polkit.subject-pid')!=str(os.getpid())):
  state.update(unexpected_action=action,detail_keys=sorted(details));save();invocation.return_dbus_error('org.freedesktop.PolicyKit1.Error.Cancelled','Unexpected test action');return
 assert caller.poll() is None and Path(f'/proc/{caller.pid}/cmdline').read_bytes().split(b'\0')[:-1]==[b'/usr/bin/pkexec',b'--disable-internal-agent',b'/usr/bin/true']
 state.update(begin_authentication=state['begin_authentication']+1,action=action,program_from_owned_caller_argv='/usr/bin/true',authority_sender_verified=True,authority_caller_pid=int(details['polkit.caller-pid']),authority_subject_pid=int(details['polkit.subject-pid']));save();pending=invocation
 window=Gtk.Window(title='Private polkit cancellation');window.set_default_size(700,250);box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=16);window.add(box)
 box.pack_start(Gtk.Label(label=message),False,False,0);box.pack_start(Gtk.Label(label='Real private polkit request: /usr/bin/true'),False,False,0)
 button=Gtk.Button(label='Cancel')
 def cancel(_):
  global pending
  state['gui_cancel']+=1;save();pending.return_dbus_error('org.freedesktop.PolicyKit1.Error.Cancelled','Cancelled by user');pending=None;window.destroy()
 button.connect('clicked',cancel);box.pack_start(button,False,False,0);window.show_all()
info=Gio.DBusNodeInfo.new_for_xml(xml).interfaces[0];bus.register_object('/org/luda/PrivateAuthenticationAgent',info,method,None,None)
start=int(Path('/proc/self/stat').read_text().rsplit(')',1)[1].split()[19]);subject=('unix-process',{'pid':GLib.Variant('u',os.getpid()),'start-time':GLib.Variant('t',start),'uid':GLib.Variant('i',os.getuid())})
bus.call_sync('org.freedesktop.PolicyKit1','/org/freedesktop/PolicyKit1/Authority','org.freedesktop.PolicyKit1.Authority','RegisterAuthenticationAgent',GLib.Variant('((sa{sv})ss)',(subject,'C.UTF-8','/org/luda/PrivateAuthenticationAgent')),None,Gio.DBusCallFlags.NONE,3000,None)
state['registered_process_pid']=os.getpid();state['registered_process_start']=start;save()
log=(out/'pkexec.log').open('w');caller=subprocess.Popen(['/usr/bin/pkexec','--disable-internal-agent','/usr/bin/true'],stdin=subprocess.DEVNULL,stdout=log,stderr=log);state['caller_pid']=caller.pid;save()
def poll():
 code=caller.poll()
 if code is not None:state['caller_exit']=code;save()
 if (out/'stop').exists():Gtk.main_quit();return False
 return True
GLib.timeout_add(50,poll);GLib.timeout_add_seconds(25,lambda:(Gtk.main_quit(),False)[1]);Gtk.main()
if caller.poll() is None:caller.terminate();caller.wait(timeout=2)
log.close()
