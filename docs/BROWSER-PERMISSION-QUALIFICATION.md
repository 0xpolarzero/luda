# Real browser permission refusal

WEB-07 asks: “Browser permission dialog: do not silently grant unrelated access”.
This fixture exercises one real geolocation prompt in a fresh owned Chromium
profile through public MCP. It does not change catalog qualification or claim
coverage of camera, microphone, notifications, file access or other browsers.

Run as an ordinary account with separately provisioned Chromium:

```sh
.venv/bin/python scripts/qualification_matrix.py --suites browser-permission \
  --executable /absolute/chrome
```

The matrix owns private Xvfb/XFWM/D-Bus/XDG state. The production
`desktop_open_browser(..., lifetime="temporary_session")` creates the browser;
the fixture serves only its authored page on loopback. A fresh origin initially
reports PermissionStatus `prompt`. Public inspection finds the request button
and its explicit `press` action; public invocation produces a trusted page event.
No permission API, Playwright grant, CDP grant, hidden prompt-answering call or
profile-preference edit supplies the permission outcome.

The browser displays the actual alert for the exact local origin: “Know your
location”, with “Allow while visiting the site”, “Allow this time”, and “Never
allow”. Public inspection links the denial button through its observed parent
chain to that origin/location alert. A public screenshot retains the visible
prompt. Before denial the oracle still says `prompt`, one request, no callback
error and zero successes. Only then does the fixture explicitly invoke the
observed denial action.

The invocation reports `effect: dispatched`, not application success. Independent
in-page PermissionStatus and the geolocation error callback establish `denied`
and `PERMISSION_DENIED` (code 1), with exactly one request and zero successes.
Public inspection also reads the page's resulting denied status. The page never
records coordinates. MCP exits cleanly; matrix cleanup verifies no tagged owned
processes remain. Host profiles, shared browser permissions and real credentials
are not involved.

## Evidence and preserved attempts

[Retained evidence](../tests/evidence/browser-permission/result.json) records
source hashes, UID1001, Ubuntu 24.04 ARM64, Chromium 153.0.8010.12, outcomes and
cleanup. The final origin-bound run `run-1789894073958825308` passed **11 checks**
in **4.042 seconds**, with unchanged source and no survivors. The
[actual prompt screenshot](../tests/evidence/browser-permission/permission-prompt.png)
is from that run. The earlier complete run passed 10 checks before the explicit
alert-ancestry assertion was added; it remains separate evidence.

Three first-attempt harness failures are retained as logs: a wrapper parameter
collided with the tool's `name` argument, a button with multiple actions required
an explicit observed action, and the reused MCP wire reader's default 64 KiB line
limit could not carry the inspection reply. The dedicated fixture now names its
wrapper parameter `tool`, chooses only observed `press` actions, and uses a
bounded 8 MiB response line limit for inspection/images. Each rerun used a fresh
owned browser. These are harness corrections, not permission-dialog retries or
browser fixes.

An absent or ambiguous real prompt fails the suite. Its observation loop is
bounded; it does not grant permissions, click guessed coordinates, accept a
page-drawn substitute or turn an unavailable prompt into a pass. The English
alert/button expectations deliberately scope this pinned fixture; localized
browser UI requires its own observed workflow.
