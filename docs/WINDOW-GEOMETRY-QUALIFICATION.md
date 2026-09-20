# Observed window geometry

`desktop_window` move, resize, maximize, restore, fullscreen and minimize results now include `observed_geometry`: client bounds, decorated frame bounds, and fixed WM state flags from fresh same-generation observations. Move compares requested frame x/y; resize compares client width/height. `request_match` is `matched` or `nonmatching`. `constraint_reason: not_determined` deliberately does not attribute an adjustment to size hints, tiling, another actor, or the application.

Observing a rectangle never upgrades `dispatched` to `verified`. A later nonmatching rectangle or WM state downgrades an earlier observed match to `dispatched`. Disappearance or generation replacement during post-dispatch reads produces a typed error with uncertain effect, rather than measurements belonging to another window. State and geometry use separate X11 reads; there is no atomicity or future stability claim.

## Local evidence

`tests/live_window_geometry.py` ran as UID1001 in a private 1200×900 Xvfb/D-Bus session with GTK3 and XFWM. All UI geometry requests used public Desktop operations. Independent `xwininfo` client coordinates/dimensions and `xprop` frame extents/state/hints checked every returned geometry and state. Six checks cover move, minimum-constrained resize, advertised increment behavior, exact resize, maximize, and restore. The restore rectangle matched the independently measured pre-maximize rectangle for this owned fixture.

The initial fixture incorrectly required all advertised increments to be enforced. Its first two runs failed that assertion: GTK advertised minimum300×180, base300×180, increments40×20; XFWM enforced request100×100 as300×180 but accepted request333×197 exactly. The second run's observations and error log are retained under `tests/evidence/window-geometry/`. The corrected assertion checks the actual behavior and matching metadata without inventing increment enforcement; it retains a mandatory minimum-constrained nonmatching case. Final passing results are retained alongside it.

Eight focused unit assertions cover constrained output, no late upgrade, later geometry/state disagreement, frame/client basis, state metadata, stale initial identity with no dispatch, and replacement during the property-read interval. Existing interaction/window-state tests also pass (31 total).

## Scope and remaining work

This is a bounded WM-02/WM-03 improvement, not release qualification. Luda does not snap sizes to hints, force a saved rectangle, or retain pre-maximize geometry across external changes. The observed restored rectangle and state are available to the caller; automatic cached restore comparison remains unimplemented because reliable invalidation across external moves/hint changes is not established. Only GTK3/XFWM/Xvfb behavior is demonstrated here, not other window managers, Silo/macOS, real display hardware, or race-free EWMH dispatch.

Run the fixture only under an isolated ordinary-account Xvfb/D-Bus session with private HOME/XDG, `LUDA_ISOLATED_TEST_DISPLAY=1` and a fresh `LUDA_GEOMETRY_OUTPUT` directory. It starts and stops only its own GTK process and XFWM; no shared desktop is used. Raw evidence contains synthetic window IDs and geometry, not user application data.
