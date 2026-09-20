# Authentication evidence audit proposal

This is a proposed interpretation and report design for review. It does not change
runtime behavior, tests, suite exit status, catalog acceptance, priority or
qualification. All catalog cases discussed here remain `unqualified`. The existing
13 probe records and original captured runs remain intact; their 9/13 result is
not a count of catalog requirements satisfied.

## Exact criteria and present evidence

| Catalog case and exact acceptance | What the fixture establishes | What is still missing |
| --- | --- | --- |
| AUTH-04: “OTP entry: preserve leading zeros and avoid retaining one-time values” | The US/French explicit digit-key workflows preserve the exact code, leave an independent clipboard owner/value unchanged, produce no complete code in responses/artifacts, and do not submit. | “Avoid retaining” needs an explicit evidence boundary. These checks establish no added clipboard/artifact copy through this route, not erasure from the destination, agent transcript, individual key arguments, memory or external listeners. No blanket nonretention qualification is justified. |
| AUTH-05: “Session expiry during workflow: detect login transition rather than act on old coordinates” | The old semantic handle is refused. Fresh inspection exposes the login transition. The deliberately stale screenshot route actually activates the replacement login control. | A positive workflow must detect the transition **before** its next mutation and avoid the old-coordinate action. The current test observes the transition only after the deliberately unsafe action, so it cannot establish that sequence. |
| AUTH-06: “OAuth new window: identify origin/session and resume the intended application” | A local popup opens, an explicit action returns to the intended opener, and an independent application state confirms completion. | The acting workflow has not identified expected origin or session through public GUI tools. The DOM fixture's origin check is application behavior, not evidence that the agent identified it. Cryptographic attestation is not stated by this criterion. |
| AUTH-07: “Credential field blocks clipboard: explicit alternate supported input or limitation” | Missing native EditableText on a masked browser field causes an explicit protected-input refusal. An unmasked digit field supports deliberate key entry. | No credential fixture currently blocks a paste event. Missing EditableText is a different cause. The exact blocked-clipboard scenario is untested; it must not inherit qualification from these adjacent probes. |
| AUTH-10: “CAPTCHA or human-presence step: expose the requirement instead of claiming automation succeeded” | Public inspection exposes the synthetic human-presence notice; the independent application state remains waiting. | This supports the synthetic human-presence variant. It does not establish detection for arbitrary CAPTCHA presentations or general challenge classification. Solving/bypassing a challenge is not required. |

AUTH-04 does not say every available input route must avoid a clipboard. A
caller-selected ordinary typing route that is documented to use CLIPBOARD should
remain a failed **route probe**, not automatically negate an independently
successful clipboard-free route. Equally, success of that alternate route must
not erase the retention failure or broaden its privacy claim. Any decision to mark
the bounded workflow satisfied should explicitly adopt the no-added-owned-copy
scope above; this proposal does not silently reinterpret “avoid retaining.”

AUTH-05 does not explicitly require a universal pixel-content guard inside every
click primitive. A demonstrated fresh-inspection workflow could satisfy its
sequence while the stale-coordinate route remains unsafe. That demonstration is
currently absent. The real wrong-intent activation is material evidence and must
remain prominent even if a safer workflow is later added.

AUTH-06 asks for origin/session identification, not a new OAuth security protocol.
The constant-false `oauth-origin-session-attestation` record imposed a stronger
criterion than the catalog. Preserve it as a historical out-of-scope assertion
and scope limitation; do not flip it to a pass. Replace its role in required
workflow coverage with an actual origin/session-identification assertion.

The protected-browser OTP failure also remains relevant to AUTH-01's explicit
secret-input path. Reclassifying it as a route diagnostic for this suite must not
hide the unresolved protected-provider capability elsewhere.

## Proposed next evidence, before changing required outcomes

1. **AUTH-04:** retain both US/French digit-key runs and add a clearly scoped
   retention statement to each workflow result. Keep the ordinary clipboard
   failure and protected-provider refusal as separately named diagnostics. Do not
   claim transcript erasure or general secret entry.
2. **AUTH-05:** use a separate fresh fixture instance. Trigger expiry through an
   observed action, inspect the resulting login notice, and stop or explicitly
   reacquire the intended login target. Independently assert that neither the old
   action nor the replacement action executed before that decision. Keep the
   current destructive-to-the-synthetic-counter probe separate and unchanged.
3. **AUTH-06:** use known distinct loopback origins and explicit visible session
   context. Through public GUI observation/read tools, identify the expected
   popup origin and session before approval; include a decoy/wrong-session popup
   and verify it is untouched. Return to the expected application and verify its
   state. The test remains a synthetic GUI workflow, not real-provider OAuth
   protocol, cryptographic or account-consent qualification.
4. **AUTH-07:** add a credential fixture that actually rejects clipboard paste.
   Observe its rejection without replaying uncertain input. Exercise a deliberately
   selected supported alternate or report the explicit limitation; independently
   verify no unintended submission or hidden partial value. Protected-field
   policy must remain unchanged. A failed general input route is not itself a
   failed criterion when the criterion expressly permits reporting a limitation.
5. **AUTH-10:** retain the current exposed-not-completed assertion with its
   synthetic human-presence scope. Do not add a requirement to solve the challenge.

These are proposed tests, not executed or passing cases. The requested safe
sequence and origin/session evidence remain missing until they actually run.

## Proposed report separation

Keep immutable legacy evidence and add explicit classification, rather than
moving failed records out of sight:

- `probe_records`: every original named check with its original `passed` value,
  measured details, source hash and run reference. Preserve all 13 records and
  prior raw runs, including the four failures.
- `required_workflows`: exact catalog ID/acceptance, bounded scope, linked probe
  IDs and outcome `passed`, `failed` or `not_run`. A missing criterion is
  `not_run`, never inferred passed from adjacent probes.
- `route_diagnostics`: original probe ID, reason it does not determine that
  workflow's success, and remaining capability/risk. Failed probes retain
  `passed: false`; unsupported is not another spelling of success.
- `scope_limits`: claims the fixture does not establish, including external
  transcript retention, real OAuth protocol qualification and arbitrary CAPTCHA
  recognition. These are not artificial executable failures.

Candidate classification of the four historical failed probes:

| Historical failed probe | Proposed classification | Required evidence it cannot replace |
| --- | --- | --- |
| `ordinary-otp-not-secret-storage` | Failed clipboard-route diagnostic; retention is real and documented. | AUTH-04's explicit scoped clipboard-free workflow and privacy boundary. |
| `browser-protected-otp-support` | Unsupported native protected-input route, retained as an AUTH-01 capability gap. | Neither general AUTH-04 nor actual clipboard-blocked AUTH-07 coverage. |
| `oauth-origin-session-attestation` | Historical out-of-scope stronger assertion; retain false and document the mismatch. | Actual GUI origin/session identification for AUTH-06, still missing. |
| `old-screenshot-after-same-window-replacement` | Failed stale-content route diagnostic with actual wrong-intent activation. | A fresh-observation-before-mutation AUTH-05 workflow, still missing. |

A future runner should exit nonzero for any required workflow failure or missing
required workflow, harness failure, source change or cleanup failure. Diagnostic
failure counts must be visible next to the required outcome. Merely classifying
the current probes would **not** justify a green auth suite: AUTH-05 and AUTH-06
lack required positive evidence, and AUTH-07 is untested if included in the suite.
No catalog priority or qualification changes are proposed.
