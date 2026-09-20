import gi,json,sys
from pathlib import Path
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,GLib
out=Path(sys.argv[1]);count=0
icon=Gtk.StatusIcon.new_from_icon_name('dialog-information');icon.set_title('Luda owned tray');icon.set_tooltip_text('Luda owned tray');icon.set_visible(True)
menu=Gtk.Menu();item=Gtk.MenuItem(label='Increment owned counter');menu.append(item);menu.show_all()
def invoke(item):
 global count
 count+=1
item.connect('activate',invoke)
def popup(icon,button,when):menu.popup(None,None,Gtk.StatusIcon.position_menu,icon,button,when)
icon.connect('popup-menu',popup)
def save():
 (out/'state.tmp').write_text(json.dumps({'embedded':icon.is_embedded(),'counter':count}));(out/'state.tmp').replace(out/'state.json');return True
GLib.timeout_add(30,save);Gtk.main()
