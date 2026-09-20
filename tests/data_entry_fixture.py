"""Owned GTK calendar, numeric constraints, validation and native completion."""
import datetime,json,locale,sys
from pathlib import Path
from zoneinfo import ZoneInfo
import gi
gi.require_version('Gtk','3.0')
from gi.repository import Gtk,GLib
locale.setlocale(locale.LC_ALL,'de_DE.UTF-8')
out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
window=Gtk.Window(title='Luda data entry oracle');window.set_default_size(650,680)
box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8);window.add(box)
def add(widget,name):
 widget.get_accessible().set_name(name);box.pack_start(widget,False,False,0);return widget
add(Gtk.Label(label='de-DE · Europe/Berlin · DD.MM.YYYY HH:MM'),'Date format and timezone')
calendar=add(Gtk.Calendar(),'Date calendar');calendar.select_month(2,2026);calendar.select_day(28)
date=add(Gtk.Entry(),'Local date and time');date.set_text('28.03.2026 12:30')
def day_changed(widget):
 year,month,day=widget.get_date();current=date.get_text().split(' ')
 date.set_text(f'{day:02}.{month+1:02}.{year:04} '+(current[-1] if len(current)>1 else '12:30'))
calendar.connect('day-selected',day_changed)
add(Gtk.Label(label='Amount: 0,00–100,00 · increment 0,01 · two decimal places'),'Numeric format and range')
amount=add(Gtk.SpinButton.new_with_range(0,100,.01),'Locale amount');amount.set_digits(2);amount.set_value(10)
city=add(Gtk.Entry(),'Destination');completion=Gtk.EntryCompletion();model=Gtk.ListStore(str)
for value in ('Berlin, Germany','Bern, Switzerland','Bergen, Norway'):model.append([value])
completion.set_model(model);completion.set_text_column(0);completion.set_minimum_key_length(2);completion.set_inline_completion(False);city.set_completion(completion)
selection=None;selection_count=0
city.connect('changed',lambda entry:clear_selection())
def clear_selection():
 global selection
 selection=None

def chosen(comp,model,iterator):
 global selection,selection_count
 value=model[iterator][0];city.set_text(value);selection=value;selection_count+=1;return True
completion.connect('match-selected',chosen)
status=add(Gtk.Label(label='Not submitted'),'Validation result')
submits=0;accepted=0;committed=None

def submit(button):
 global submits,accepted,committed
 submits+=1
 try:
  local=datetime.datetime.strptime(date.get_text(),'%d.%m.%Y %H:%M');tz=ZoneInfo('Europe/Berlin')
  choices=[local.replace(tzinfo=tz,fold=fold) for fold in (0,1)]
  valid=[value for value in choices if value.astimezone(datetime.timezone.utc).astimezone(tz).replace(tzinfo=None)==local]
  if not valid:raise ValueError('Date/time does not exist in Europe/Berlin')
  if len({value.utcoffset() for value in valid})>1:raise ValueError('Date/time is ambiguous in Europe/Berlin')
  amount.update()
  committed={'utc':valid[0].astimezone(datetime.timezone.utc).isoformat(),'amount':amount.get_value(),'amount_text':amount.get_text(),'destination':city.get_text(),'selected_suggestion':selection}
  accepted+=1;status.set_text('Accepted')
 except ValueError as exc:status.set_text(str(exc))
button=add(Gtk.Button(label='Submit'),'Submit data');button.connect('clicked',submit)

def save():
 year,month,day=calendar.get_date()
 state={'locale':locale.setlocale(locale.LC_NUMERIC),'decimal_point':locale.localeconv()['decimal_point'],'timezone':'Europe/Berlin','calendar':[year,month+1,day],'date_text':date.get_text(),'amount':amount.get_value(),'amount_text':amount.get_text(),'destination':city.get_text(),'completion_prefix':completion.get_completion_prefix(),'completion_enabled':completion.get_popup_completion(),'entry_focused':city.has_focus(),'selected_suggestion':selection,'selection_count':selection_count,'submits':submits,'accepted':accepted,'validation':status.get_text(),'committed':committed}
 (out/'state.tmp').write_text(json.dumps(state));(out/'state.tmp').replace(out/'state.json');return True
GLib.timeout_add(20,save);window.connect('destroy',Gtk.main_quit);window.show_all();date.grab_focus();Gtk.main()
