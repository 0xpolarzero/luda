# Large table and lazy-tree qualification

A real GTK3 fixture exposes 1,200 model rows, two visible columns, sorting, filtering, an editable cell renderer, and a tree whose children are populated only after expansion. The model is held in memory; this is a viewport-managed native table, not proof of support for every remotely virtualized or infinite data source. Related DATA-01/02/04 requirements remain broader than this fixture.

The test runs as an ordinary UID in private Xvfb/D-Bus/XFWM and fresh XDG directories. Actual public `Desktop` operations drive the UI. The application separately persists selected stable record ID, model order/count, visible row range, committed edits, actual editor visibility, lazy-loaded children, and actual expanded state. No test directly edits its model.

The initial completed run on 2026-09-20 passed **13 of 14 checks** and exited 1 because its only editable-cell attempt used the ineffective semantic action. A later observed GUI workflow succeeds, as detailed below. Source hash `550f1e9819ca977f63161036826611afe4396c3a5cbebd6b1a19e1c856c5337b` was unchanged. Local evidence is `artifacts/data`, including initial failures and corrected fixture/precondition runs.

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

## Cropped names and stale identity

A public accessible name is limited to 300 characters. Reusing that shortened value as the complete identity could allow a recycled path whose meaning changed only after character 300. Handles now privately retain a SHA256 fingerprint of the full unprotected accessible name; the public inspection output never contains the fingerprint. Names larger than one MiB of UTF-8 are refused before hashing, and the character budget is checked before encoding. AT-SPI itself returns a whole native name, so this is a post-retrieval identity-processing bound, not a claim to bound the provider's native reply allocation. Protected names are neither read nor hashed.

Changed full-name identity refuses mutation with `STALE_TARGET`. An oversized identity fails with `TARGET_IDENTITY_UNAVAILABLE`; omitted unreadable nodes mark inspection incomplete. Provider paths reused with identical full names and roles still cannot be distinguished without a provider generation identifier; process identity, window scope and handle expiry remain necessary safeguards.

The real fixture added a button whose accessible name changes only after character 300. Its old handle refused before the independent click counter changed; a fresh handle worked and exposed no digest. That run passed 15/16 checks, retained the grid-edit failure, and kept source hash `ba959a421c398e904125e54838e4096d854da29fbca1cd973aaf5a21ca8fec99` unchanged. Seven focused tests cover suffix identity, stale dispatch prevention, byte budget, protected-name privacy, fixed diagnostics, private handle storage, and incomplete inspection.

## Successful editable-cell GUI workflow

The further GUI qualification used current screenshot coordinates mapped from the observed visible cell, double-click/F2 to enter editing, explicit select-all/paste, and Return to commit. The saved screenshot visibly shows the row-zero editor. The independent application oracle confirms the editor is mapped and focused before text input; afterward exactly record zero has the requested Japanese/emoji value, the editor is closed, and the model still contains 1,200 rows. A fresh public semantic read of the committed cell independently returns the exact payload. No model mutation driver or direct widget setter supplies the text.

The transient editor itself is genuinely omitted from this GTK accessibility tree. A read-only diagnostic traversed all 2,417 provider nodes without budget/depth pruning or unreadable branches and found no editable/focused entry. A bounded [AT-SPI Collection query](https://docs.gtk.org/atspi2/method.Collection.get_matches.html) also found none. These probes did not justify weakening production traversal bounds or inventing a semantic editor handle.

The final `data-controls` matrix run passed **16/16 required workflow checks** in 37.179 seconds. It separately records three unsuccessful provider-path diagnostics: the semantic edit action's missing editor, inaccessible transient-editor discovery, and the dependent semantic-editor typing path. Those diagnostics retain `passed=false` with explicit unsupported/blocked statuses in `provider_diagnostics`; none is relabeled a supported capability. Prior failed runs remain saved. DATA-04 requires distinguishing cell editing from whole-widget replacement and completing the edit, so a demonstrated screenshot/clipboard/commit/readback workflow satisfies this fixture without requiring a nonexistent semantic editor.

Matrix source hash `597b44a40ccb233ac466a971f399d229d9a7d60dca7f56b5d1822d99c22bc089` remained unchanged; cleanup left no survivors. This is qualification of one GTK fixture, not automatic global qualification of the DATA catalog.

```sh
.venv/bin/python scripts/qualification_matrix.py --suites data-controls
```

`tests/data_collection_probe.py` is a diagnostic for the owned synthetic fixture; it is not a runtime capability or a means of mutating the UI.
