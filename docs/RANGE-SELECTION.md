# Observed GTK list/table range selection

The additive `range_end_id` argument selects an inclusive range using existing
`desktop_choose`. Scalar choice behavior remains unchanged. This evidence covers
a synthetic GTK3 ListBox and two-column TreeView through actual public MCP tools,
with independent app-persisted row IDs, selected sets and change counters.

The final fixture contains 120 table records and 20 list options. It exercises
range replacement, reversed endpoints, extending, idempotency, disabled/offscreen
refusal, focus loss, sort/filter staleness, duplicate labels, application sorting
or recycling a row during selection, and an actual SINGLE-mode table. The latter
must stop with uncertain partial progress after its first incompatible action;
absence of the provider's MULTISELECTABLE state is not assumed to mean SINGLE.

Both providers preserve exact requested sets in MULTIPLE mode even though GTK's
table omits the capability flag. Selection is not an application save/commit.
Captured AT-SPI bus generation/provider/path/full-name identity does not prove
stable business-record identity when an app reuses exactly the same exposed
identity. Current-state rechecks cannot prevent all concurrent app changes.

The first runs are retained, including a refusal caused by an overly strict
MULTISELECTABLE guard and a 1200-row table exhausting the existing 1600-node
inspection budget before a later ListBox could be reached. The dedicated range
fixture was reduced to 120 rows; the original data-controls fixture retains 1200
rows. No traversal budget was enlarged and unobserved rows remain unsupported.
Other early fixture failures were a helper argument collision and an assumed
button action name; the final fixture uses observed/default actions.

Run as an ordinary user:

```sh
.venv/bin/python scripts/qualification_matrix.py --suites range-selection
```

The runner owns a private Xvfb, D-Bus and XDG session. It records source hashes,
process cleanup and full suite results. This is a provider/workflow sample, not
universal virtualized selection support or catalog qualification.

Additional real probes found both GTK ListBox individual deselection APIs leave
the selection unchanged. Those failed runs remain retained. The final primary
replacement plan uses `clear_selection`, verifies an empty set, then adds the
requested range and verifies each addition. Clearing is one `selection_step`,
not one step per removed item. Extension preserves existing choices, and an
already exact set is a no-op. No failed removal triggers a fallback or replay.
The selected-slot mutation lookup no longer exists. A unit regression also
covers app reorder during selected-set readback, refused before any action.

Final live run `1789898578487119289` passed in 13.010 seconds: 25 result records
(16 named workflows plus 9 explicit refusal receipts), with unchanged source
fingerprint `603ecc1ad37cb409242801b419a4a8f8b2ec242b8d78e13dd299d8e71a349c59` and no surviving owned processes.
Full original and final reports/logs are retained under
`tests/evidence/range-selection/`. Documentation/evidence capture followed the run;
the retained file hashes bind the tested runtime and fixture independently.
