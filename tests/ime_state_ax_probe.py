"""Read-only synthetic-fixture AT-SPI evidence; never changes IME state."""
import json
import sys
import gi
gi.require_version('Atspi','2.0')
from gi.repository import Atspi,Gio,GLib
import xml.etree.ElementTree as ET
session=Gio.bus_get_sync(Gio.BusType.SESSION,None)
address=session.call_sync('org.a11y.Bus','/org/a11y/bus','org.a11y.Bus','GetAddress',None,GLib.VariantType.new('(s)'),Gio.DBusCallFlags.NONE,1000,None).unpack()[0]
bus=Gio.DBusConnection.new_for_address_sync(address,Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT|Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION,None,None)
Atspi.set_timeout(600,1000)
pid=int(sys.argv[1]);queue=[Atspi.get_desktop(0)];results=[]
for _ in range(200):
    if not queue:break
    node=queue.pop(0)
    if node.get_process_id()==pid and node.get_name()=='Composition field':
        result={'states':[s.value_nick for s in node.get_state_set().get_states()],'attributes':node.get_attributes(),'interfaces':node.get_interfaces()}
        if 'Text' in result['interfaces']:
            text=node.get_text_iface();count=Atspi.Text.get_character_count(text)
            result['text']=Atspi.Text.get_text(text,0,count)
            result['text_attributes']=[Atspi.Text.get_attribute_run(text,i,True)[0] for i in range(count)]
        result['accessible_id']=node.get_accessible_id();result['provider']=node.app.bus_name;result['path']=node.path
        xml=bus.call_sync(node.app.bus_name,node.path,'org.freedesktop.DBus.Introspectable','Introspect',None,GLib.VariantType.new('(s)'),Gio.DBusCallFlags.NONE,1000,None).unpack()[0]
        if len(xml)>131072:raise RuntimeError('Introspection budget exceeded')
        result['dbus_interfaces']={i.attrib['name']:{kind:[m.attrib['name'] for m in i.findall(kind)] for kind in ('method','signal','property')} for i in ET.fromstring(xml).findall('interface')}
        results.append(result)
    queue.extend(node.get_child_at_index(i) for i in range(min(node.get_child_count(),100)))
print(json.dumps(results,ensure_ascii=False))
