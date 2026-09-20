"""Synthetic selection/password controls. Only secret hashes leave fixture memory."""
import hashlib
import json
from pathlib import Path
import sys
kind=sys.argv[1];out=Path(sys.argv[2]);out.mkdir(parents=True,exist_ok=True)
def persist(state):
 state['normal_widget_type']=type(normal).__name__
 (out/'state.tmp').write_text(json.dumps(state));(out/'state.tmp').replace(out/'state.json')
if kind=='qt':
 from PyQt5 import QtWidgets,QtCore
 app=QtWidgets.QApplication([]);w=QtWidgets.QWidget();w.setWindowTitle('Luda controls Qt');w.resize(500,430)
 box=QtWidgets.QVBoxLayout(w)
 secret=QtWidgets.QLineEdit();secret.setEchoMode(QtWidgets.QLineEdit.Password);secret.setAccessibleName('Control secret');box.addWidget(secret)
 normal=QtWidgets.QLineEdit();normal.setAccessibleName('Control normal');box.addWidget(normal)
 disabled=QtWidgets.QLineEdit();disabled.setEchoMode(QtWidgets.QLineEdit.Password);disabled.setAccessibleName('Disabled secret');disabled.setEnabled(False);box.addWidget(disabled)
 choices=QtWidgets.QListWidget();choices.setSelectionMode(QtWidgets.QAbstractItemView.MultiSelection)
 choices.addItems(['Option one','Option two','Option three']);box.addWidget(choices)
 radios=[QtWidgets.QRadioButton(x) for x in ('Radio one','Radio two')]
 for radio in radios:box.addWidget(radio)
 radios[0].setChecked(True)
 combo=QtWidgets.QComboBox();combo.setAccessibleName('Control combo');combo.addItems(['Color red','Color blue']);box.addWidget(combo)
 def save():persist({'secret_hash':hashlib.sha256(secret.text().encode()).hexdigest(),'normal':normal.text(),'selected':[x.text() for x in choices.selectedItems()],'radio':[x.isChecked() for x in radios],'combo':combo.currentText()})
 timer=QtCore.QTimer();timer.timeout.connect(save);timer.start(30);w.show();app.exec()
else:
 import gi
 gi.require_version('Gtk','3.0')
 from gi.repository import Gtk,GLib
 w=Gtk.Window(title='Luda controls GTK');w.set_default_size(500,430)
 box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6);w.add(box)
 secret=Gtk.Entry();secret.set_visibility(False);secret.get_accessible().set_name('Control secret');box.pack_start(secret,False,False,0)
 normal=Gtk.Entry();normal.get_accessible().set_name('Control normal');box.pack_start(normal,False,False,0)
 disabled=Gtk.Entry();disabled.set_visibility(False);disabled.set_sensitive(False);disabled.get_accessible().set_name('Disabled secret');box.pack_start(disabled,False,False,0)
 choices=Gtk.ListBox();choices.set_selection_mode(Gtk.SelectionMode.MULTIPLE)
 for name in ('Option one','Option two','Option three'):
  row=Gtk.ListBoxRow();row.get_accessible().set_name(name);row.add(Gtk.Label(label=name));choices.add(row)
 box.pack_start(choices,True,True,0)
 radios=[Gtk.RadioButton.new_with_label_from_widget(None,'Radio one')]
 radios.append(Gtk.RadioButton.new_with_label_from_widget(radios[0],'Radio two'))
 for radio in radios:box.pack_start(radio,False,False,0)
 combo=Gtk.ComboBoxText();combo.get_accessible().set_name('Control combo');combo.append_text('Color red');combo.append_text('Color blue');combo.set_active(0);box.pack_start(combo,False,False,0)
 def save():
  persist({'secret_hash':hashlib.sha256(secret.get_text().encode()).hexdigest(),'normal':normal.get_text(),'selected':[r.get_accessible().get_name() for r in choices.get_selected_rows()],'radio':[r.get_active() for r in radios],'combo':combo.get_active_text()});return True
 GLib.timeout_add(30,save);w.connect('destroy',Gtk.main_quit);w.show_all();Gtk.main()
