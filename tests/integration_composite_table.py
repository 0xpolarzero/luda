"""Real GTK composite table selection with an independent application oracle.

Run under a disposable display/session, for example:
  dbus-run-session -- xvfb-run -a /usr/bin/python3 tests/integration_composite_table.py
This fixture creates and closes only its own window; no installed settings change.
"""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]


def fixture(output):
    import gi
    gi.require_version('Gtk', '3.0')
    from gi.repository import Gtk
    model = Gtk.ListStore(bool, str)
    for name in ('First choice', 'Requested choice', 'Last choice'):
        model.append([False, name])
    view = Gtk.TreeView(model=model)
    column = Gtk.TreeViewColumn('Choices')
    # Two renderers force GtkContainerCellAccessible around the named text cell.
    toggle = Gtk.CellRendererToggle()
    text = Gtk.CellRendererText()
    column.pack_start(toggle, False)
    column.add_attribute(toggle, 'active', 0)
    column.pack_start(text, True)
    column.add_attribute(text, 'text', 1)
    view.append_column(column)
    def changed(selection):
        current_model, selected = selection.get_selected()
        value = current_model[selected][1] if selected is not None else None
        output.write_text(json.dumps({'selected': value}))
    view.get_selection().connect('changed', changed)
    window = Gtk.Window(title='Luda composite cell fixture')
    window.set_default_size(400, 250)
    window.add(view)
    window.connect('destroy', Gtk.main_quit)
    window.show_all()
    Gtk.main()


def main():
    import gi
    gi.require_version('Atspi', '2.0')
    from gi.repository import Atspi
    spec = importlib.util.spec_from_file_location('luda_ax_worker', ROOT / 'src/luda/ax_worker.py')
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    with tempfile.TemporaryDirectory(prefix='luda-composite-') as temporary:
        output = Path(temporary) / 'state.json'
        env = dict(os.environ, GTK_MODULES='gail:atk-bridge', NO_AT_BRIDGE='0')
        process = subprocess.Popen(['/usr/bin/python3', __file__, '--fixture', str(output)], env=env)
        try:
            deadline = time.monotonic() + 8
            node = None
            while time.monotonic() < deadline:
                for candidate, _ in worker.candidates(process.pid):
                    if candidate.get_name() == 'Requested choice' and candidate.get_role_name() == 'table cell':
                        node = candidate
                        break
                if node is not None:
                    break
                time.sleep(.05)
            assert node is not None, 'Named renderer not exposed by GTK'
            table = Atspi.TableCell.get_table(node.get_table_cell()).get_table_iface()
            row, column = Atspi.TableCell.get_position(node.get_table_cell())[-2:]
            canonical = table.get_accessible_at(row, column)
            assert canonical.path != node.path, 'Fixture did not create a composite cell'
            assert node.get_parent().path == canonical.path, 'Renderer parent is not canonical cell'
            observation = worker.table_cell_observation(node)
            result = worker.choose_table_row(node, worker.describe(node, process.pid), False,
                                             {'target': {'table_cell': observation, 'parent_path': canonical.path}})
            assert result.get('effect') == 'verified', result
            deadline = time.monotonic() + 3
            oracle = None
            while time.monotonic() < deadline:
                try:
                    oracle = json.loads(output.read_text())
                    if oracle.get('selected') == 'Requested choice':
                        break
                except (FileNotFoundError, json.JSONDecodeError):
                    pass
                time.sleep(.025)
            assert oracle == {'selected': 'Requested choice'}, oracle
            print(json.dumps({'renderer': node.path, 'canonical': canonical.path,
                              'row': row, 'column': column, 'result': result, 'oracle': oracle}))
        finally:
            process.terminate()
            process.wait(timeout=3)


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--fixture':
        fixture(Path(sys.argv[2]))
    else:
        main()
