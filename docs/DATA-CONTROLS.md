# Large table and lazy-tree qualification

A real GTK3 fixture exposes 1,200 model rows, two visible columns, sorting, filtering, an editable cell renderer, and a tree whose children are populated only after expansion. The model is held in memory; this is a viewport-managed native table, not proof of support for every remotely virtualized or infinite data source. Related DATA-01/02/04 requirements remain broader than this fixture.

The test runs as an ordinary UID in private Xvfb/D-Bus/XFWM and fresh XDG directories. Actual public `Desktop` operations drive the UI. The application separately persists selected stable record ID, model order/count, visible row range, committed edits, actual editor visibility, lazy-loaded children, and actual expanded state. No test directly edits its model.

The final run on 2026-09-20 passed **13 of 14 checks** and deliberately exited 1 for the remaining editable-cell capability. Source hash `550f1e9819ca977f63161036826611afe4396c3a5cbebd6b1a19e1c856c5337b` was unchanged. Local evidence is `artifacts/data`, including initial failures and corrected fixture/precondition runs.

| Case | Result |
|---|---|
| Inspection limit of 500 over large table | Passed; truncation and traversal budget reported |
| Name filter does not imply full-tree coverage | Passed; matching output still reports traversal pruning |
| Offscreen row | Refused before selection; independent selected record unchanged |
| Visible row | Exact row selected and independently verified |
| Sort followed by old handle | Refused `STALE_TARGET` |
| Filter removes previously observed record | Refused `STALE_TARGET` |
| Lazy expand, fresh child inspection, collapse | Passed against actual widget state |
| Setting text directly on a cell | Refused; no whole-table or model replacement |
| Enter and commit editable cell | **Failed**: advertised `edit` action accepted, but no editor opened and no model value changed |
| Screenshot-anchored scrolling | Visible row range changed from 0–20 to 20–41 |
| Fresh inspection after scroll | Selected a viewport-intersecting row by its observed stable meaning |

GTK keeps `SHOWING` on some offscreen table cells while returning `G_MININT` screen coordinates. Luda therefore requires intersecting cell/container extents before semantic row choice. A caller should scroll first, then inspect afresh; `SHOWING` alone is not a reliable viewport filter for this provider.

GTK's generic `Selection.select_child` did not select table rows. `desktop_choose` now uses the explicit TableCell/Table row-selection interfaces for table cells, verifies the observed cell's position, path and name against the table, and checks the resulting selected-row set. Choosing a cell selects its **whole row**. `extend=true` preserves other rows; the default normalizes to one selected row. Recycled meaning or position cannot produce verified success in the focused fault tests. Provider acceptance without the expected selected rows remains uncertain. This adds no generic row search, unbounded traversal, arbitrary grid editing or hidden-row activation.

The first fixture also needed two infrastructure corrections: keep the lazy placeholder until its replacement children exist so expansion is not canceled by an empty model, and query actual expanded state rather than trusting a signal flag. The original logs remain available. The final grid failure is not merely inaccessible inspection: the independent oracle reports `editing_widget_visible=false` after the accepted action. No blind text input follows it.

Run with a worktree-local venv, ordinary UID, and writable artifact directory:

```sh
LUDA_ISOLATED_TEST_DISPLAY=1 xvfb-run -a -s '-screen 0 1440x1000x24 -nolisten tcp' \
  dbus-run-session -- .venv/bin/python tests/live_data.py
```

The fixture owns XFWM. Six unit regressions additionally cover exclusive/extended row selection, offscreen refusal, ignored acceptance, recycled meaning after selection, and invalid cell position. The final full unit suite passed 446 tests.
