# Synthetic authentication qualification

`tests/live_auth.py` drives a local browser fixture exclusively through public
MCP tools. Playwright launches the browser, loads the initial local page and reads
DOM state as an independent oracle; it does not fill, click, mutate or navigate
the workflow. Requests outside the loopback fixture are aborted. No real account,
credential, OAuth provider or CAPTCHA is involved.

Run as the ordinary desktop user:

```sh
.venv/bin/python scripts/qualification_matrix.py --suites auth --executable /path/to/chromium
```

The matrix supplies private Xvfb, D-Bus and XDG state, records source hashes and
cleans up owned processes. Results contain booleans, interface names and error
codes, not the synthetic one-time value or complete tool responses.

## Observed results

On Linux ARM64, UID 1001 and Chromium 153.0.8010.12, the final run recorded **7/11
passing checks and exited 1**. Its source fingerprint was
`a51a506f2db62c42b08d8d27e66fb164c9b676cdc8c0e908df01f2fecd613d30`, unchanged
through the 6.859-second run. Artifacts remain under
`artifacts/qualification-matrix/run-1789871136270121701/` in the qualification
worktree. Earlier complete runs preserve the same limitations. The first partial
run used an unsupported guessed button action; the harness was corrected to use
only the provider's observed activation action, not to conceal a product failure.

| Requirement | Evidence | Remaining limit |
| --- | --- | --- |
| AUTH-04 OTP | Unmasked `type=tel` input preserves leading zeros; explicit submission clears the fixture field; ordinary type response does not echo the value. Protected-only input correctly refuses this unmasked field. | Clipboard inspection independently confirms the value remains in CLIPBOARD. This is not a nonretaining OTP path. The browser's masked field also refuses explicit secret input because native EditableText is absent. |
| AUTH-05 expiry | Same-window login replacement invalidates the old semantic handle with `STALE_TARGET`; fresh inspection exposes the expiry notice. | An old screenshot's coordinate still dispatches after replacement with unchanged geometry. The fixture places a new login action at the old button position; the independent action counter increments once. Window/surface identity does not prove unchanged content or intent. |
| AUTH-06 new window | Observed activation opens a local authorization window; its explicit action closes it, updates the intended opener and returns to the original window. | Titles and visible UI do not provide trusted OAuth origin/session attestation. This synthetic flow does not qualify real OAuth security or account consent. |
| AUTH-10 human presence | Fresh inspection exposes the synthetic human-presence requirement, and the app remains waiting for the user. | This is observable presentation, not generic challenge classification, solving or bypass. |

No one-time literal appeared in the final run's result files or captured MCP
server log. That does **not** establish absence from caller transcripts, process
memory, clipboard managers or all diagnostic systems. The clipboard retention is
an explicit observed failure, not an expected-failure pass. The suite retains all
four failed checks and remains nonzero.

## Input design implications

The qualified unmasked `type=tel` field exposes Text, Component and Action but no
EditableText. There is no native semantic setter to select instead of the current
clipboard path. The masked browser field has the same practical secret-input gap.
Changing the existing protected-only tool to silently accept visible fields would
remove an intentional targeting safeguard.

A future explicit sensitive-input capability could admit an observed unmasked
editable field only when the caller deliberately requests that policy. It must
refuse providers lacking a qualified input mechanism, avoid text readback and
clipboard ownership, sanitize errors, and report acceptance/dispatch rather than
secret verification. A separate digit-only keyboard path may be feasible for OTP
fields with verified focus and supported key mappings, but requires tests for
selection, replacement, interrupted input, focus races, leading zeros and no
implicit submission. It is not implemented or qualified here. Do not restore an
old clipboard blindly: asynchronous consumers and human clipboard changes make
that a separate ownership problem.

Agents should reobserve after login transitions and use fresh semantic targets.
Current screenshot expiry/geometry checks do not guarantee content freshness.
Any stronger stale-content guard needs a separate design with animation,
caret-blink, overlays and human-input races considered; this fixture does not
justify claiming screenshot input has been made atomic.
