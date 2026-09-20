# Broad opt-in qualification matrix

`scripts/qualification_matrix.py` runs 22 existing suites with separate Xvfb, session D-Bus and private XDG config/data/cache/runtime directories for each suite. It is opt-in and refuses UID 0. It supplements the stable native-app and headless CI runners; it does not replace them or run authenticated agent evaluations.

```sh
.venv/bin/python scripts/qualification_matrix.py --list

.venv/bin/python scripts/qualification_matrix.py \
  --suites semantic protected-options browser-offsets \
  --executable /absolute/path/to/chromium

.venv/bin/python scripts/qualification_matrix.py --all \
  --executable /absolute/path/to/chromium
```

`LUDA_CHROMIUM_EXECUTABLE` is the alternative to `--executable`. The IME browser probe now also requires its browser executable explicitly. No browser download or credential provisioning occurs. The account running the command needs write access to the worktree's `artifacts` directory; source and venv can remain read-only to that account. Run as the actual ordinary desktop account, using `runuser -u silo-desktop -- ...` only when invoking from an authorized root development shell. Do not run the matrix through an existing desktop's display environment.

`--all` or `--suites` is required. `--list` reports scripts, related requirement IDs, toolkit dependencies, known gaps and which suites own their window manager. The default per-suite deadline is 180 seconds; `--timeout` accepts 1..300. Known gaps are explanatory metadata only: failed assertions, nonzero exits, timeouts, missing dependencies, cleanup failures and source changes all make the final exit nonzero. There is no “expected failure” success category.

## Isolation and evidence

The runner removes inherited display, Xauthority, session/AT-SPI bus, input-method and session-manager selectors before starting a private session. It keeps the account's real home unchanged. Desktop state directories are created mode 0700 before D-Bus starts. Most suites receive a runner-owned XFWM4; IME and full XFCE lifecycle suites start their own window manager. Suites that create disposable X servers also keep their existing server lifecycle. No second window manager is started on their display.

The existing process-group cleanup helper is reused. In addition, a random inherited invocation token identifies same-UID descendants that create new sessions. Cleanup revalidates process start identity before signalling those processes and reports any live tagged survivors. This is containment for cooperating local fixtures, not a security sandbox against processes deliberately erasing the token or escaping ownership. No process-name/global kill is used.

A timestamped batch directory under `artifacts/qualification-matrix/` retains:

- Per-suite command, dependency checks, duration, exit/status, cleanup and before/after source hashes.
- Full stdout/stderr logs and newly written suite artifacts, copied into the batch before later runs can overwrite legacy artifact paths.
- Batch environment/package/browser version evidence and full source fingerprints.

The diagnostic imports check distro GTK3/GTK4, AT-SPI and PyQt5 where needed; command checks name missing binaries. Browser paths must exist and be executable. Existing suite output remains unchanged, including distinctions between supported, unsupported, failed and blocked toolkit cases. A suite passing an explicit-refusal test does **not** establish support for the refused operation.

Related requirement IDs are navigation aids for reviewing the underlying assertions, not complete coverage claims. The runner never edits the acceptance catalog or automatically changes requirement qualification.

## First broad run, 2026-09-20

The immutable first run used commit `3ba2029`, based on main `611f419`, in `/workspace/luda-matrix` with its own venv. It ran as `silo-desktop` (UID 1001) on ARM64 Ubuntu with the configured local Chromium executable. All 22 suites ran: **16 passed, 6 failed**. There were no dependency omissions, timeouts, reported cleanup survivors or source changes. The process exited 1.

Passing suites: semantic, protected-options, combos, browser-offsets, mcp-reconnect, x11-isolation, window-tokens, window-metadata-capacity, window-metadata, geometry, clipboard-interference, drag, popup, resource-stress, application-launch and application-services.

| Failed suite | Observed result |
| --- | --- |
| toolkits | Qt 29 supported; GTK4 window appeared before the accessibility provider and its initial scoped-tree observation failed. See the separate readiness investigation below. |
| browser | 25/26 checks passed. Rich contenteditable `semantic-replace-editable` remained unsupported for exact verification. |
| rich-copy | 31/43 assertions passed; lossy rich-text serialization and caret restoration remain blockers. |
| ime | Actual pending composition established in all 12 GTK scenarios; conflicting-input guards remain unsupported. |
| ime-browser | Actual key-driven composition established in all 6 Chromium scenarios; conflicts remain unguarded. |
| accessibility-lifecycle | 17/18 assertions passed. The existing GTK application's accessibility bridge did not reconnect after the actual private accessibility bus restarted. |

The original evidence is `run-1789865913323837377/results.json`. Its before/after source hash is `9ce52e0fb40f667b7e7d2e21d9b86d7a1265f0f6c9b46d2588911eed1495d014`. No result was discarded or converted to success because a failure was already known.

## Separate GTK4 registration investigation

The first failed GTK4 raw scope was empty; its fixture log contained only software-rendering/EGL warnings. An independent read-only probe recreated the same private environment and ordinary UID. The real X11 window existed at 0.558 seconds after launch while inspect returned `ACCESSIBILITY_UNAVAILABLE`; at 0.893 seconds, the same window exposed 11 scoped nodes, remaining available through 8.15 seconds. This directly demonstrated delayed provider registration rather than a geometry mismatch or permanently unsupported toolkit.

Commit `d2d72f0` adds a four-second read-only readiness precondition to `live_toolkits.py`. It waits for the exact fixture editor in the selected accessible window. It retries only absence (`ACCESSIBILITY_UNAVAILABLE` or an incomplete tree), preserves failure after the deadline, and immediately propagates ambiguous mapping or other errors. It never retries a mutation. Readiness attempts are persisted independently. Four deterministic tests cover delayed registration, timeout, incomplete trees and ambiguity refusal.

A separate toolkit-only matrix run, `run-1789866216396881522`, recorded GTK4 unavailable at 0.053 and 0.208 seconds of the readiness wait, then ready at 0.390 seconds. With that precondition satisfied, the prior capability results returned: Qt 29 supported; GTK4 21 supported, 2 unsupported, 3 provider failures and 3 dependent blocked cases. The suite still exited 1. Its source hash was unchanged at `1532fce4e76c896d7d2825a2874290a2086350a53424694fdaf3a8efb91183a6`.

The first broad failure remains intact, alongside this narrower follow-up. This was a startup precondition correction justified by an independent observation, not repeated application actions until an outcome happened to pass.

Eight deterministic runner tests additionally cover failure propagation, timeout and detached descendants, cleanup isolation, environment separation, requirement-ID validity, missing-browser diagnostics and window-manager ownership. The matrix's scope is the listed local suites; it does not establish architecture parity, production reliability, actual VM suspend/resume, or remote Mac/SSH onboarding.
