# Observed window geometry

`desktop_window` move, resize, maximize, restore, fullscreen and minimize results now include `observed_geometry`: client bounds, decorated frame bounds, and fixed WM state flags from fresh same-generation observations. Move compares requested frame x/y; resize compares client width/height. `request_match` is `matched` or `nonmatching`. `constraint_reason: not_determined` deliberately does not attribute an adjustment to size hints, tiling, another actor, or the application.

Observing a rectangle never upgrades `dispatched` to `verified`. A later nonmatching rectangle or WM state downgrades an earlier observed match to `dispatched`. Disappearance or generation replacement during post-dispatch reads produces a typed error with uncertain effect, rather than measurements belonging to another window. State and geometry use separate X11 reads; there is no atomicity or future stability claim.

## Local evidence

`tests/live_window_geometry.py` ran as UID1001 in a private 1200×900 Xvfb/D-Bus session with GTK3 and XFWM. All UI geometry requests used public Desktop operations. Independent `xwininfo` client coordinates/dimensions and `xprop` frame extents/state/hints checked every returned geometry and state. Six checks cover move, minimum-constrained resize, advertised increment behavior, exact resize, maximize, and restore. The restore rectangle matched the independently measured pre-maximize rectangle for this owned fixture.

The initial fixture incorrectly required all advertised increments to be enforced. Its first two runs failed that assertion: GTK advertised minimum300×180, base300×180, increments40×20; XFWM enforced request100×100 as300×180 but accepted request333×197 exactly. The second run's observations and error log are retained under `tests/evidence/window-geometry/`. The corrected assertion checks the actual behavior and matching metadata without inventing increment enforcement; it retains a mandatory minimum-constrained nonmatching case. Final passing results are retained alongside it.

Eight focused unit assertions cover constrained output, no late upgrade, later geometry/state disagreement, frame/client basis, state metadata, stale initial identity with no dispatch, and replacement during the property-read interval. Existing interaction/window-state tests also pass (31 total).

## Scope and remaining work

This is a bounded WM-02/WM-03 improvement, not release qualification. Luda does not snap sizes to hints or force a saved rectangle. The bounded historical comparison described below detects observed changes; it does not establish continuous external-change history. Only GTK3/XFWM/Xvfb behavior is demonstrated here, not other window managers, Silo/macOS, real display hardware, or race-free EWMH dispatch.

Run the fixture only under an isolated ordinary-account Xvfb/D-Bus session with private HOME/XDG, `LUDA_ISOLATED_TEST_DISPLAY=1` and a fresh `LUDA_GEOMETRY_OUTPUT` directory. It starts and stops only its own GTK process and XFWM; no shared desktop is used. Raw evidence contains synthetic window IDs and geometry, not user application data.

## Historical maximize/restore comparison

`maximize` captures prior client/frame bounds only for a normal window with stable pre-action measurements, observed successful maximization and matching normal-size hints. Its `observed_geometry.restore_reference` reports `captured` or `unknown`. An explicit `restore` returns `observed_geometry.restore_comparison` with `matched`, `nonmatching`, or `unknown`, separate from the WM-state effect. A match compares both actual rectangles with the historical reference; it is not a geometry-setting action or a promise of future stability. Nonmatching does not downgrade an otherwise verified WM-state change, and matching never upgrades a dispatched change.

References use the exact opaque window generation, remain local to the backend and have no short expiry. At most64 are retained; eviction, missing observations, window replacement, close and reconnect remove references. Repeating maximize preserves a reference only while current maximized state, geometry, workspace and normal hints still match. Other explicit geometry/state commands invalidate it even if the resulting geometry happens to match; raise-only does not. Window enumeration invalidates references when it observes different rectangles/workspace. Restore consumes its reference and checks current hints/state before and after dispatch. Unknown results include a fixed reason; they do not attribute a constraint to the application or WM.

There is no persistent X11 event monitor. An external restore/move/hint change followed by a return to the same observed values between checks can go undetected. The result explicitly identifies this as historical same-generation comparison. Providers reusing the exact same exposed state between separate reads cannot be made atomic by this cache.

`tests/live_restore_comparison.py` passed seven grouped checks as ordinary UID1001 under private Xvfb/D-Bus/HOME/XDG. Independent `xwininfo`/`xprop` measurements cover minimum-constrained resize, repeated maximize and matching restore, changed minimum hints yielding unknown, external unmaximize/move yielding unknown, own unchanged-workspace command invalidation, a replacement window receiving no stale restore, and backend-close cleanup. The hints case remained maximized in XFWM; the result retained dispatched WM state and unknown comparison. The separate external-move case uses a fresh owned fixture, never retries that uncertain action. Early fixture failures and this behavior are retained in `tests/evidence/restore-comparison/`.

Run as an ordinary user with a writable artifacts directory:

```sh
.venv/bin/python tests/live_restore_comparison.py
```

The harness creates its own private session. Focused tests additionally cover nonmatching comparisons, an observed change-and-revert, missing hints, cache eviction, post-restore hints changes and lifecycle contracts. This increment supplies useful scoped WM-03 behavior, not universal restore preservation or catalog qualification.
