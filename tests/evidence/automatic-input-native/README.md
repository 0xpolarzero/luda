# Automatic-input native regression evidence

Validation ran against runtime commit `0bca5e0` on private Xvfb/XFWM desktops,
using explicit ordinary account `ubuntu` (UID 1000), separate D-Bus sessions,
and each worktree's own virtual environment. The agent cursor used its enabled
default, including fresh native element location before feedback. No shared
`:1` desktop was used. This is fixture regression evidence, not production or
catalog qualification.

| Check | Result |
| --- | --- |
| Public background routing | 7 passed, including simultaneous foreground user typing, minimized target fallback, and application-requested foreground |
| GTK3 native semantic operations | 35 passed |
| GTK3 list/table ranges through MCP | 24 passed, including stale/disabled/partial-failure refusals and background selection preserving foreground |
| Nested GTK3 menu | Passed: callback wrote exact file proof; cancelled, occluded, and vanished targets refused |
| Detached GTK3 menus | 7 passed |
| GTK4 GUI alternatives through MCP | 5 passed, verified with application state, screenshots, and exact readback |
| GTK4 semantic toolkit fixture | 21 supported, 2 unsupported, 3 provider failures, 3 dependent blocked cases |
| Qt5 semantic toolkit fixture | Accessibility scope unavailable; no Qt action qualified in this environment |

The toolkit suite exited 1. A separate worktree and virtual environment at
baseline `385f1c7` reproduced **the same per-case statuses and error codes**:
Qt accessibility scope unavailable and GTK4 `select`, `caret-zero`, and
`astral-select` returning `ACCESSIBILITY_ERROR`. Both complete JSON reports are
retained. This establishes these observed limitations also exist on the
baseline; it does not establish the cause of Qt's unavailable provider.

Initial run evidence is retained under `initial/`. The existing range test
expected background selection to fail with `FOCUS_CHANGED`; its assertion was
updated to require verified selection and unchanged foreground. The GTK4 GUI
test initially inspected before AT-SPI registration; it now retries only that
read-only startup observation for up to four seconds. All subsequent mutation
failures remain unreplayed. The updated suites passed.

Reproduction uses the retained `runner.py` with an explicit worktree argument:

```sh
runuser -u ubuntu -- env LUDA_ISOLATED_TEST_DISPLAY=1 \
  dbus-run-session -- xvfb-run -a \
  -s '-screen 0 1440x1000x24 -nolisten tcp' \
  /absolute/worktree/.venv/bin/python \
  /absolute/worktree/tests/evidence/automatic-input-native/runner.py \
  /absolute/worktree live_semantic.py live_toolkits.py \
  live_range_selection.py live_menu.py live_detached_menu.py
```

The worktree's `artifacts` directory must be writable by the selected test
account. The runner starts and closes its own window manager. The background
suite starts its own manager and uses the same private Xvfb/D-Bus command with
`tests/live_background_routing.py` directly. GTK4 GUI creates its own private
session: run `tests/live_gtk4_gui.py --output /absolute/output` under that account.

Package versions are retained in `packages.txt`. JSON records contain only
synthetic fixture text. Background desktop observations are sampled; they do
not prove absence of every transient focus change or broad toolkit support.
