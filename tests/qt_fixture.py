"""Offline Qt5 qualification app; state comes from toolkit objects, not AT-SPI."""
import json
import sys
from pathlib import Path
from PyQt5 import QtWidgets, QtCore
out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
app=QtWidgets.QApplication([])
w=QtWidgets.QWidget();w.setWindowTitle('Luda Qt Fixture');w.resize(620,480)
layout=QtWidgets.QVBoxLayout(w)
editor=QtWidgets.QTextEdit();editor.setAccessibleName('Toolkit text');layout.addWidget(editor)
check=QtWidgets.QCheckBox('Toolkit check');layout.addWidget(check)
value=QtWidgets.QSlider(QtCore.Qt.Horizontal);value.setRange(0,100);value.setAccessibleName('Toolkit value');layout.addWidget(value)
secret=QtWidgets.QLineEdit();secret.setEchoMode(QtWidgets.QLineEdit.Password);secret.setAccessibleName('Toolkit secret');layout.addWidget(secret)
disabled=QtWidgets.QPushButton('Toolkit disabled');disabled.setEnabled(False);layout.addWidget(disabled)
button=QtWidgets.QPushButton('Open toolkit dialog');layout.addWidget(button)
modal=None;dialog_count=0
def show_modal():
 global modal,dialog_count
 modal=QtWidgets.QDialog(w);modal.setWindowTitle('Luda Qt Modal');modal.setModal(True)
 box=QtWidgets.QVBoxLayout(modal);box.addWidget(QtWidgets.QLabel('Synthetic modal content'))
 close=QtWidgets.QPushButton('Close toolkit dialog');box.addWidget(close);close.clicked.connect(modal.accept)
 dialog_count+=1;modal.show()
button.clicked.connect(show_modal)
def save():
 text=editor.toPlainText();cursor=editor.textCursor()
 state={'text':text,'checked':check.isChecked(),'value':value.value(),
        'caret_utf16':cursor.position(),'selection_utf16':[cursor.selectionStart(),cursor.selectionEnd()],
        'focused':editor.hasFocus(),'dialog_visible':bool(modal and modal.isVisible()),'dialog_count':dialog_count}
 (out/'state.tmp').write_text(json.dumps(state,ensure_ascii=False));(out/'state.tmp').replace(out/'state.json')
timer=QtCore.QTimer();timer.timeout.connect(save);timer.start(30)
w.show();editor.setFocus();app.exec()
