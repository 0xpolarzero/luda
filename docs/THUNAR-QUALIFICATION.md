# File manager qualification

`tests/live_thunar.py` drives Thunar 4.18.8 through Luda's desktop API on
Linux ARM64/X11/Xfwm4. It exercises nine filesystem-backed assertions:

- Create a Unicode folder and cancel creation of another folder.
- Rename the folder and cancel a proposed rename.
- Copy/paste a file containing binary bytes, Unicode and emoji exactly.
- Cancel a duplicate-file conflict, then explicitly replace the destination.
- Cancel permanent deletion, then explicitly confirm deletion of the copy.

Every case checks independent filesystem state. Copy and deletion also
verify the original source remains byte-for-byte intact. Tests observe the
replacement or permanent-deletion dialog before making the decision. Input
is dispatched through Luda, not a file-manager automation API. Fixture setup
and disk readback use Python; this deliberately separates the UI action
from its verification oracle.

## Current evidence

All nine filesystem assertions passed in two diagnostic runs that retried
a read-only `wmctrl -lp` `BadWindow` race. The committed test deliberately
does not contain that workaround. With unmodified runtime, a subsequent
run reproduced the enumeration error during dialog dismissal and exited
nonzero. This is a runtime reliability blocker, not a successful end-to-end
qualification; rerun after the enumeration fix before marking the suite
qualified. No mutating action was retried in any run.

## Isolation and invocation

Install test dependencies into `.venv` and provide a writable
`artifacts/thunar`. Run as an ordinary user, with private XDG directories
set **before** starting the D-Bus session, so configuration services also
use private paths:

```sh
private_dir=$(mktemp -d)
trap 'rm -rf "$private_dir"' EXIT
export XDG_CONFIG_HOME="$private_dir/config"
export XDG_DATA_HOME="$private_dir/data"
export XDG_CACHE_HOME="$private_dir/cache"
xvfb-run -a -s '-screen 0 1440x1000x24 -nolisten tcp' \
  dbus-run-session -- bash -c '
    xfwm4 --compositor=off > /tmp/luda-thunar-wm.log 2>&1 &
    wm_pid=$!
    trap "kill $wm_pid 2>/dev/null || true" EXIT
    .venv/bin/python tests/live_thunar.py
  '
```

All documents and directories are temporary fixtures. The test launches and
terminates its own Thunar process. It explicitly requests permanent deletion
of its copied fixture, so no existing user trash is read or modified.
Results and the most recent synthetic accessibility tree are saved under
`artifacts/thunar`. Unexpected failures are recorded and exit nonzero.

A native app CI job is practical: install `thunar`, `mousepad`, `xfwm4`,
`xvfb`, `dbus-x11` and the documented Luda system dependencies during runner
setup; use an ordinary runner account and the isolation above. This avoids
installing applications during normal user-desktop operation. Such a job
can run the Thunar and Mousepad suites without downloading a browser.

This is bounded local qualification, not coverage of all file-manager
operations. Drag/drop, cut/move, trash restoration, mounts, network locations,
large asynchronous transfers, thumbnail generation, permissions UI and
localized dialog labels remain outside this suite. The session has no
thumbnail service, which causes harmless Thunar diagnostic messages; exact
file-operation oracles pass without it. MCP transport is covered separately.
