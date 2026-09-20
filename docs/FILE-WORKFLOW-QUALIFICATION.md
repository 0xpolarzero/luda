# Native file workflow qualification

The local run passed all ten assertions:

- Save As to an existing Unicode filename opens the replacement dialog.
  Cancel preserves the old bytes; an independent explicit Replace scenario
  writes the exact multiline Unicode/emoji value and preserves the source.
- Closing a modified document first leaves its original window present and
  disk content untouched. Cancel keeps the document open; a subsequent save
  proves the edited buffer survived. Don't Save closes with the old bytes;
  Save closes with the new bytes.
- Saving over a file in a non-writable directory produces Mousepad's visible
  read-only refusal, preserving both the protected target and source bytes.

A button invocation is not proof of a completed transition. The suite polls
native window state, fresh accessibility trees and file contents. The
replacement dialog must be observed before choosing Cancel or Replace.
Cancellation and replacement use independent editor processes. Assertions
on close occur after the relevant native window disappears, not merely when
its confirmation dialog appears.

## Running

Install the project and test dependencies into `.venv`. Run from the project
root as an ordinary desktop user with access to Xvfb, Xfwm4, D-Bus, AT-SPI,
Mousepad, the Luda system dependencies and a writable `artifacts/files`.
Root is rejected because it bypasses the permission fixture.

```sh
xvfb-run -a -s '-screen 0 1440x1000x24 -nolisten tcp' \
  dbus-run-session -- bash -c '
    xfwm4 --compositor=off > /tmp/luda-files-wm.log 2>&1 &
    wm_pid=$!
    trap "kill $wm_pid 2>/dev/null || true" EXIT
    .venv/bin/python tests/live_file_workflows.py
  '
```

The test owns all temporary documents and launched Mousepad processes. It
uses private XDG directories and an in-memory GSettings backend for Mousepad,
restores permission bits before deleting fixtures, and terminates only apps
it launched. When using shared display `:1` instead, hold
`/tmp/luda-live-tests.lock` for the entire invocation. The isolated Xvfb run
does not access that desktop.

Results are written to `artifacts/files/results.json`; the most recent
synthetic accessibility tree is `last-tree.json` for diagnosis. A premature
suite failure is recorded explicitly and the process exits nonzero. These
artifacts contain synthetic fixture names and text. The read-only refusal
can cause Mousepad's GTK accessibility provider to print ATK warnings; the
read-only message and unchanged-file oracles still passed locally.
