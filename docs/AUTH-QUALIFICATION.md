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

The [evidence audit proposal](AUTH-EVIDENCE-AUDIT.md) compares these probe outcomes
with the exact catalog criteria. The approved follow-up below documents the resulting report separation and
exit policy; original records and catalog qualification remain unchanged.

## Observed results

On Linux ARM64, UID 1001 and Chromium 153.0.8010.12, the original full run recorded **7/11
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

No one-time literal appeared in that run's result files or captured MCP
server log. That does **not** establish absence from caller transcripts, process
memory, clipboard managers or all diagnostic systems. The clipboard retention is
an explicit observed failure, not an expected-failure pass. Those original runs retain all
four failed checks and remain recorded as nonzero. The later scoped workflow
report described below does not rewrite their outcomes.

## Input design implications

The qualified unmasked `type=tel` field exposes Text, Component and Action but no
EditableText. There is no native semantic setter to select instead of the current
clipboard path. The masked browser field has the same practical secret-input gap.
Changing the existing protected-only tool to silently accept visible fields would
remove an intentional targeting safeguard.

An existing deliberate keyboard workflow now provides a tested alternative for
this visible digit-only field. It does not broaden the protected-only tool or
introduce another secret API. Any future native sensitive-input capability would
still need explicit policy, supported provider mechanisms and acceptance-only
semantics. Do not restore an old clipboard blindly: asynchronous consumers and
human clipboard changes make that a separate ownership problem.

## Clipboard-free digit-key workflow

The added first-attempt US and French cases both passed using existing public
tools: focus the observed visible OTP field, deliberately replace its contents
with Ctrl+A and BackSpace, then send each digit through `desktop_press_keys`.
The fixture configures the private display's layout before each case; Luda does
not change the user's layout. No text readback tool, clipboard tool, DOM mutation,
or implicit submission is used in this route.

An independent foreground xclip owner supplies a sentinel before input. Raw Xlib
selection-owner identity, process lifetime and clipboard contents remain unchanged
after each workflow. A read-only DOM SHA-256 comparison verifies the exact code
including leading zeros without returning its plaintext to the controller. The
application submission counter stays zero. Captured responses contain no complete
one-time literal, and artifacts contain neither that literal nor its digest.

The expanded run records **9/13 passing checks and exits 1**: both new workflows
pass, while the four original failures remain unchanged. It ran as UID 1001 with
Chromium 153.0.8010.12 on ARM64 in 12.367 seconds, with unchanged source fingerprint
`89361a149f38a873797d7f8c068a7e1e924a98ffa4af4ea32b23a3a4e6440bbd` and no surviving owned processes. Evidence is in
`artifacts/qualification-matrix/run-1789872355266767366/` in the qualification
worktree.

This avoids the observed clipboard retention; it does not prove absence from the
application, caller/tool transcript, memory, key listeners or all logging systems.
An agent still supplies the digits as tool arguments. Key tools verify dispatch
and input cleanup, not the secret value. Separate calls are not atomic and do not
bind focus to the same element throughout the sequence. Other layouts, segmented
OTP widgets, auto-advancing fields, composition and application-specific shortcuts
need their own qualification. This is a deliberate authorized workflow for visible
input, not automatic recovery from a refused protected-field operation.

Agents should reobserve after login transitions and use fresh semantic targets.
Current screenshot expiry/geometry checks do not guarantee content freshness.
Any stronger stale-content guard needs a separate design with animation,
caret-blink, overlays and human-input races considered; this fixture does not
justify claiming screenshot input has been made atomic.

## Scoped workflows and preserved diagnostics

After the criterion audit, the approved follow-up adds actual missing workflow
evidence instead of treating all possible input routes as required successes:

- **AUTH-05:** a separate fresh fixture expires its session, refuses its old
  semantic handle, then exposes the login notice through fresh inspection. The
  independent old-action, replacement-action and submission counters all remain
  zero. This is the safe observation sequence; the separate old-screenshot probe
  still activates the replacement login control and remains a failed diagnostic.
- **AUTH-06:** before approving the popup, public browser-chrome text establishes
  its full scheme/host/port and public inspection establishes the expected visible
  app/popup session. After approval, public inspection reads the returned app's
  session-specific completion status; the independent DOM oracle agrees.

The browser initially omits the scheme even after Ctrl+L. Runs that could not
establish it refused approval; their failed/blocked results remain captured.
The address-bar context menu's items were absent from scoped AX, but its retained
screenshot visibly showed **Always show full URLs** as the final item. One
public End/Return sequence selected it in the disposable profile. Subsequent
public text readback included the scheme; no HTTP scheme was inferred, no CDP
preference was set, and no user browser profile was changed. The fixture records
this screenshot-dependent menu path and setting/readback result. Menu order in
another browser/version is not qualified by this pinned fixture.

The final run has **4/4 scoped required workflows passing, 12/16 total probes
passing, and four failed diagnostics preserved**. AUTH-04 covers only the
explicit visible-digit workflow and measured storage boundary; AUTH-10 covers
only the synthetic exposed human-presence step. AUTH-07 remains explicitly
unexercised, and all catalog qualifications remain `unqualified`.

The report retains every probe in `cases`, maps exact acceptance strings and
probe IDs under `required_workflows`, and preserves failed original values under
`route_diagnostics`. The latter distinguish the OTP clipboard route, unsupported
protected provider, stale-coordinate activation and the historical stronger
cryptographic-attestation assertion. None becomes a supported capability.

The new exit policy is nonzero for a failed/missing required workflow, any
unclassified failed probe, a duplicate or omitted expected probe, or harness
failure. Matrix source-change and cleanup checks continue to apply. It permits
zero when the scoped workflows succeed despite explicitly classified route
limitations. This is why the final run exits zero; it does **not** mean all auth
requirements, routes or providers are qualified. Six deterministic report tests
ensure failures or omitted diagnostics cannot be hidden by classification.

The final 16.410-second ordinary-UID run used unchanged source fingerprint
`af362f65e7d2229da7a2f74b5f926aed9b56058d7f5fe1896dc3eb55e87b2370`, with no owned
process survivors. Evidence is retained in
`artifacts/qualification-matrix/run-1789873145058039909/`. Earlier failed/blocked
runs, including the first full-URL menu probe, are retained alongside it.

The earlier context-menu screenshot also shows Chrome echoing the deliberately
retained **synthetic** OTP in its Paste-and-search item. That is additional visible
evidence of the ordinary clipboard route's limitation, not a private/user secret;
the original screenshot remains preserved. Later popup probes explicitly install
an independent test clipboard sentinel to isolate this separate workflow. This
fixture setup is not a production clipboard-restore policy or a claim that the
original clipboard route avoids retention. Final popup screenshots show the
sentinel; the latest captured text records do not contain the complete OTP.
