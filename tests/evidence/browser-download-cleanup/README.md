# Temporary browser attachment cleanup: independent evidence

This is a narrow real-browser fault probe, not a production change or a general
claim about all downloaded files. A loopback-only HTTP fixture serves an authored
33-byte attachment. Public MCP `desktop_open_browser` opens the page in a temporary
session. Before each fault the probe independently finds the exact attachment
bytes inside the owned profile, records descendant PID/start-time identities and
checks the caller's temporary directory. It then tests stdin EOF, browser-worker
SIGKILL and MCP-server SIGKILL separately. Within eight seconds the owned profile
must disappear and the tracked processes must exit; no attachment may remain in
the caller's temporary directory. A test-only cleanup runs after assertions and
cannot turn a failing cleanup assertion into a passing result.

## Retained sequence

- `original/leak-probe.py` and `original/leak.log`: the earlier independent direct
  worker probe found a real 33-byte attachment under caller TMPDIR both before and
  after cleanup proof `b'1'`. That is the original external-temporary-file leak,
  not a hypothetical missing assertion. These scripts retain historical absolute
  paths for provenance; use the adapted harness below for new runs.
- `original/long-socket-path.log`: intermediate containment attempt failed during
  Chromium startup with `Socket path too long`. It never established a successful
  attachment precondition and is not counted as cleanup evidence.
- `original/three-case-probe.py`, `three-case.log`, `three-case-result.json`: the
  corrected independent public-MCP probe passed all three cases as UID1001,
  independently finding the attachment before each failure. Exact fixed guard
  SHA256: `d0087f91f88dc14e962f0292a846bd50a1bc96cc692d002a051924c143031b4e`.
- `reproduced/result.json` and `session.log`: the parameterized harness in this
  directory reran successfully on Linux ARM64 as UID1001 against Luda47b4bce,
  Chromium153.0.8010.12 and Playwright1.63.0. All three source hashes match the
  original corrected result; each case tracked15 descendants with no survivors.

The earlier short-root direct probe only listed caller TMPDIR and did not prove
an actual attachment existed before cleanup. It is deliberately not used as a
passing attachment cleanup result.

## Reproduce

Use a disposable checkout with its own `.venv`: `uv sync --frozen --extra browser`.
Install ordinary test dependencies Xvfb/xvfb-run, xauth, dbus-run-session, xfwm4,
wmctrl and the system libraries required by your existing Chromium. No browser is
downloaded by this harness. Run as an ordinary test account with read/execute
access to the checkout/venv and a writable, fresh output directory:

```sh
python3 tests/evidence/browser-download-cleanup/run.py \
  --repo /absolute/luda-checkout \
  --chromium /absolute/existing/chromium \
  --output /absolute/owned/evidence/new-run
```

`run.py` refuses UID0 and creates a new Xvfb, D-Bus session and private HOME/XDG
paths before launching any desktop process. It binds HTTP only to loopback,
never accesses an ordinary user's browser profile, and limits the whole run to90
seconds. The caller TMPDIR is deliberately long; the XDG runtime root is short
and private, respecting Unix socket path limits. `probe.py` reuses this repository's
actual MCP wire/process helpers and selected checkout's `.venv/bin/luda`; it does
not simulate cleanup. Run results include exact source hashes. Existing output
should be preserved separately when comparing versions. This evidence does not
cover explicit persistent downloads, machine/power loss, every browser build or
macOS, nor does it prove cleanup of untracked arbitrary external processes.
