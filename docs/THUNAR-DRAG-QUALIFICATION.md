# Thunar drag intent and cancellation

`tests/live_thunar_drag.py` exercises the exact PTR-09 criterion, “Drag onto
file manager: distinguish copy/move/link and confirmation dialog”, with real
Thunar 4.18.8, ordinary UID 1001, private Xvfb/XFWM/D-Bus/XDG, and actual public
MCP tools. It does not change catalog qualification or require a new input API.

Two temporary, owned folders contain a synthetic binary payload. Each workflow
uses a fresh pair of folders. The test observes the source filename in Thunar's
native detailed-list view, derives its drag point from AX bounds, and calls
`desktop_drag_to(button='right')` into the observed destination client. The
native menu visibly offers **Copy here**, **Move here**, **Link here**, and
**Cancel**; no transfer has occurred before the deliberate menu choice.

The source remains active after the drag. A direct destination click is refused
with `FOCUS_CHANGED`, with files untouched. Explicitly activating the destination
preserves the menu. A fresh observation must retain the same popup identity and
bounds before clicking the chosen row. The confirmation dialog's Cancel button
is independently inspected and invoked through AX.

Independent filesystem checks establish:

- Copy preserves both exact byte sequences and creates a distinct inode.
- Move removes the source and preserves exact bytes and inode on this filesystem.
- Link creates a symlink resolving to the preserved source, with exact bytes.
- Native drag-menu Cancel leaves the source unchanged and destination empty.
- Copy onto an existing same-name file opens the real replacement dialog; Cancel
  preserves both original byte sequences and inodes without extra destination files.

The tool's drag result remains `dispatched`; these assertions belong to the
fixture's independent oracle, not a claim that input dispatch verifies a transfer.

## Evidence and limitations

The first full five-workflow run passed all 11 assertions in 24.941 seconds:
`/workspace/luda-thunar-drag/artifacts/qualification-matrix/run-1789874633401136577`.
Adding the explicit inactive-destination refusal regression produced 12/12 in
24.910 seconds in `run-1789874688625269979`. The matrix retains full screenshots,
scoped trees, outcomes, source fingerprints, and cleanup diagnostics per run.
Earlier startup/argument errors, the omitted icon-view file, an incomplete menu
probe, and the initially refused unactivated click remain in earlier run archives;
they have not been rewritten as passes. The final stricter popup-identity run is
recorded alongside them. The initial identity guard incorrectly compared the
observation-local `popup_id`; its failing run `run-1789874763295122056` is
preserved. The corrected guard compares XID, PID/start, generation, owner,
transient relationship, and bounds across observations.

This is an observed, fixed-theme workflow, not a universal menu locator. Thunar's
icon view omitted file children from AX; Ctrl+2 exposes the file in detailed-list
view. Both scoped trees also omitted the drag action menu. Row coordinates are
therefore derived from the retained screenshot and fresh popup origin, with an
explicit 129×117 native-pixel geometry guard. In these runs activation sometimes
left the action labels temporarily blank, while the same menu identity, bounds,
row targets, and file effects remained intact. Pre-activation screenshots preserve
the visible action labels. This rendering limitation is not semantic menu support.
Changed themes, localization, additional menu entries, cross-filesystem moves,
remote filesystems, modifier-based dragging, and conflict Replace are untested here.
The ordinary file-operation suite separately tests deliberate Replace via clipboard.

Run on an installed test-only Thunar environment:

```sh
runuser -u desktop -- .venv/bin/python scripts/qualification_matrix.py \
  --suites thunar-drag --timeout 90
```

Every failed assertion or harness error exits nonzero. All application-driving
operations use existing public MCP tools; direct file access only seeds the owned
fixtures and independently checks effects.
