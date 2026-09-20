"""System-GI helper: query registered services without activating or unlocking them."""
import json
import os


def collect():
    import gi
    gi.require_version('Gio','2.0')
    from gi.repository import Gio,GLib
    result=[]
    flags=Gio.DBusCallFlags.NO_AUTO_START
    def invoke(bus,name,path,interface,method,args=None):
        return bus.call_sync(name,path,interface,method,args,None,flags,400,None).unpack()
    try:session=Gio.bus_get_sync(Gio.BusType.SESSION,None)
    except GLib.Error:session=None
    for name,path in [('org.xfce.ScreenSaver','/org/xfce/ScreenSaver'),('org.gnome.ScreenSaver','/org/gnome/ScreenSaver'),('org.freedesktop.ScreenSaver','/org/freedesktop/ScreenSaver')]:
        item={'provider':name,'kind':'screensaver','available':False}
        try:
            if session is None:raise ValueError()
            active=invoke(session,name,path,name,'GetActive')[0]
            if not isinstance(active,bool):raise ValueError()
            item.update(available=True,active=active)
        except (GLib.Error,ValueError,IndexError):item['reason']='unavailable'
        result.append(item)
    identity=os.environ.get('XDG_SESSION_ID')
    if identity:
        item={'provider':'org.freedesktop.login1','kind':'lock_hint','available':False}
        try:
            bus=Gio.bus_get_sync(Gio.BusType.SYSTEM,None)
            path=invoke(bus,'org.freedesktop.login1','/org/freedesktop/login1','org.freedesktop.login1.Manager','GetSession',GLib.Variant('(s)',(identity,)))[0]
            active=invoke(bus,'org.freedesktop.login1',path,'org.freedesktop.DBus.Properties','Get',GLib.Variant('(ss)',('org.freedesktop.login1.Session','LockedHint')))[0]
            if isinstance(active,GLib.Variant):active=active.unpack()
            if not isinstance(active,bool):raise ValueError()
            item.update(available=True,active=active)
        except (GLib.Error,ValueError,IndexError):item['reason']='unavailable'
        result.append(item)
    return result

if __name__=='__main__':
    try:print(json.dumps(collect()))
    except Exception:print(json.dumps([{'provider':'query','available':False,'reason':'unavailable'}]))
