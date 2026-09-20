# P1 capability audit at 7783721

> Historical record from before Editor Bridge became a separate add-on. Tool names, source paths and test commands below describe the recorded revision, not the current core installation. For current setup and supported behavior, see [Editor Bridge](../addons/editor-bridge/README.md).

Read-only review of the 30 P1 cases in [requirements.json](requirements.json):
window management (WM), authentication (AUTH), and forms/tables (DATA).
This is an implementation planning order, not a catalog priority change,
qualification decision, or new test result. References below distinguish
production behavior from synthetic fixtures and missing environment evidence.
The scope is the existing XFCE/X11 desktop and optional owned browser.

## Smallest useful next increments

| Order / exact catalog IDs | Concrete current gap or limit | Smallest useful change | Meaningful independent oracle |
| --- | --- | --- | --- |
| 1 — **WM-09**, “Launch known app: return actual window identity with bounded readiness”; **WM-10**, “Already-running singleton app: associate new request with correct existing/new window” | `desktop_launch` returns desktop-service acceptance and optional spawn PIDs. It does not return a ready window or associate a singleton request with its receiving window. This is an honest production limitation, not lack of a launch implementation. | Add an explicit bounded observation phase after one launch, returning proven candidate window identities and an ambiguous/pending outcome when association cannot be established. Preserve raw dispatched status and never relaunch on timeout. Start with direct-spawn PID/start identity; leave D-Bus singleton association unknown unless a request/window link is actually available. | Extend the existing singleton fixture with two same-process windows, a delayed requested document and a decoy title. Its independent open-request log and per-window document ID must agree with any association returned. Timeout must not duplicate the request. |
| 2 — **WM-02**, “Resize window: account for app minimum size and size increments”; **WM-03**, “Maximize and restore: preserve prior geometry and report resulting state” | `manage_window` compares resize to the exact requested size, and restore verification checks state flags only. Results omit actual accepted geometry. A constrained resize can remain dispatched without showing the agent the useful accepted size; restore does not independently prove the previous rectangle. | Return freshly observed client/frame bounds and WM state for geometry actions. Explicitly distinguish exact request match from constrained observed result. For driver-initiated maximize, retain the prior rectangle by native generation and compare it after restore; if external changes invalidate the comparison, report that rather than impose an old rectangle. | An owned GTK window with minimum/increment hints; independent X geometry before maximize and after restore; resize to a nonconforming size. Include external move/hint change and window replacement to prevent reuse of obsolete geometry. |
| 3 — **DATA-03**, “Multi-selection: explicit replace/add/range semantics and verify selected items” | `desktop_choose(element_id, extend)` implements exclusive/additive list/table selection; there is no explicit semantic range selection contract. Repeated additive calls are not a range operation and can partially complete. | Add an explicit bounded range mode only for a single verified list/table container, using two observed endpoints and revalidating ordering/meaning before input. Return the resulting selected set and partial/uncertain state if the provider changes. Do not silently interpret numeric indices as durable identity. | Multi-select GTK list/table with sorted and filtered states. Independently compare selected stable record IDs; exercise reversed endpoints, offscreen endpoints, disabled rows and sorting during selection. |
| 4 — **AUTH-01**, “Password entry: explicitly supported secret-input path without plaintext readback or logs”; **AUTH-07**, “Credential field blocks clipboard: explicit alternate supported input or limitation” | Native protected EditableText works, but the tested browser password field lacks it. The owned-browser provider also exposes protected fields as unsupported. AUTH-07 already has evidence for the explicit-limitation alternative; successful browser secret entry is still absent. | Consider a narrowly scoped protected-field route in the owned browser through the existing secret tool. Require current protected type, document/element identity, focus and known inactive composition; no clipboard, ordinary readback, plaintext response or automatic submit. Report dispatch only unless acceptance can be checked without exposing the value. Keep ordinary text APIs refusing protected fields. | Local password fixture with actual paste blocking, protected-to-unprotected replacement, focus theft and a decoy field. Independent in-app hash comparison and submission counter; assert secret absent from all tool/history/error/report outputs and clipboard unchanged. No real credentials. |
| 5 — **AUTH-06**, “OAuth new window: identify origin/session and resume the intended application” | A generic public-GUI synthetic OAuth workflow already passes, including URL/session observation. However the optional owned browser deliberately refuses text operations when more than one page or a frame exists. An ordinary auth popup therefore removes its semantic text capability. | Add explicit enumeration/selection of owned top-level pages bound to exact native-window and opener/document identities before considering frames. Expose origin as browser-observed metadata, not identity-provider attestation. Ambiguous page/window association must refuse. No automatic approval, popup switching or credential reuse. | Two local origins, expected popup plus a same-title decoy, native/public selection of the intended popup, navigation replacement, close and return to opener. Independent per-session completion/counter must prove decoy untouched. |
| 6 — **DATA-07**, “Rich text editor: distinguish plain text content from markup and formatting” | Production now supports arbitrary code-point selection and explicit clipboard replacement in cooperating basic ProseMirror paragraphs. It is no longer accurate to list all middle-range editing as missing. Actual documents with hard breaks, links, lists, tables or custom nodes remain refused. | Extend the declared cooperating schema one feature at a time, starting with hard breaks only if explicit line-break semantics and offset mapping can remain unambiguous. Preserve existing paragraph behavior; do not reinterpret LF automatically. Generic opaque editors remain outside that contract. | Actual ProseMirror native/clipboard edit with hard breaks adjacent to paragraph boundaries, marks and emoji. Compare application document JSON, visible/read text and exact unaffected nodes; unsupported mixed content must refuse before mutation. |
| 7 — **DATA-01**, “Virtualized table rows: scroll and reacquire item identity rather than reuse index” | Existing 1,200-row GTK evidence is a viewport-managed native table, not an infinite/recycled remote data source. Scroll/reinspect and stale sort/filter refusal work; a general semantic search-through-virtualization helper is absent. This is primarily missing representative evidence, not a reason to replace working primitives immediately. | First qualify a genuinely recycled asynchronous row fixture using existing observe/scroll/inspect/choose. Only if agent navigation is materially blocked, add an explicit bounded search-and-scroll operation with a maximum scroll budget, progress/absence distinction and no hidden-row activation. | Reuse the same provider paths for different stable record IDs while loading delayed pages; record the actual selected application ID and each loaded page. Test duplicate labels, end-of-data, no-progress and filter changes. |
| 8 — **AUTH-08**, “System authentication dialog: distinguish privileged operation from ordinary application input” | The VM lacks the system bus/polkit authority/agent needed for the real workflow. Current ordinary protected-field support cannot establish privileged-dialog identity. This is blocked environment evidence, not proof that a new production API is required. | Use a disposable image with a real existing authority and an owned graphical agent; inspect a benign request and explicitly cancel. Do not add guessed title-based classification or alter production auth policy to make the test pass. Add structured privileged-context metadata only if authoritative provenance can actually be read. | Benign `pkexec /usr/bin/true`, no credentials; correct owned dialog observed, explicit Cancel, caller exit and no privileged callback independently confirmed. Ensure no pre-existing agent is replaced. |

## Code and existing evidence behind the ranking

- **WM-09/10:** [apps.py](../src/luda/apps.py),
  [_app_helper.py](../src/luda/_app_helper.py) and
  [APPLICATIONS.md](APPLICATIONS.md). `live_application_services.py` already
  proves terminal launch, singleton request delivery and timeout without killing
  the existing singleton. It does not make returned PID hints into window readiness.
- **WM-02/03:** [Interaction.manage_window](../src/luda/interaction.py) and
  [live_interaction.py](../tests/live_interaction.py). The current live loop checks
  accepted WM states; this proposal concerns accepted geometry and historical
  restore comparison, not replacing the existing maximize/minimize implementation.
- **DATA-03:** [desktop_choose](../src/luda/server.py),
  [ax_worker.py](../src/luda/ax_worker.py) (`choose_table_row` and selection paths),
  [live_mcp_controls.py](../tests/live_mcp_controls.py), and
  [DATA-CONTROLS.md](DATA-CONTROLS.md). Exclusive/additive/idempotent behavior and
  visible table-row selection have real and focused evidence.
- **AUTH-01/07:** [owned field metadata and protected refusal](../src/luda/_browser_worker.py),
  [desktop_type_secret](../src/luda/server.py), and the final
  [clipboard-blocking credential section](AUTH-QUALIFICATION.md#clipboard-blocking-credential-field-auth-07).
  Earlier statements that AUTH-07 was unexercised are historical, not current gaps.
- **AUTH-06:** [_browser_worker.Worker.check](../src/luda/_browser_worker.py)
  single-page/frame checks and the completed
  [scoped auth workflows](AUTH-QUALIFICATION.md#scoped-workflows-and-preserved-diagnostics).
  Generic GUI origin/session evidence exists; cryptographic OAuth attestation is
  not silently added to the criterion.
- **DATA-07:** [current cooperating bridge contract](../addons/editor-bridge/README.md),
  [_browser_worker.py](../src/luda/_browser_worker.py),
  [live_owned_rich_clipboard.py](../addons/editor-bridge/tests/live_owned_rich_clipboard.py).
  The updated clipboard range behavior supersedes old gap-audit summaries that
  called all middle selection unsupported.
- **DATA-01:** [DATA-CONTROLS.md](DATA-CONTROLS.md) explicitly scopes its model and
  demonstrates offscreen refusal, fresh identity after scroll and sort/filter
  invalidation. No catalog-level virtualized-data guarantee follows automatically.
- **AUTH-08:** [SYSTEM-AUTH-ENVIRONMENT.md](SYSTEM-AUTH-ENVIRONMENT.md) preserves
  exact missing prerequisites and the unexecuted real-dialog workflow.

## Important boundaries, not additional missing-tool claims

**AUTH-05:** a fresh-inspection expiry workflow already passes. The retained
old-screenshot diagnostic really activates a replacement control. Current native
identity/layout/age checks cannot establish unchanged intent. The evidence does
not justify a generic pixel-difference guard that would reject animated UI or
claim session identity from pixels; keep explicit reobservation after transitions.

**DATA-04:** the GTK cell's advertised semantic edit action failed independently,
but the observed double-click/F2 → paste → explicit Return workflow now commits
and reads back the intended cell. A provider-specific semantic gap remains; a
universal grid-edit API is not established as necessary by that evidence.

**DATA-05/06/08/09:** current locale/date, raw numeric-versus-formatted value,
validation-error and autocomplete workflows have
[actual MCP/application-oracle evidence](DATA-ENTRY-QUALIFICATION.md). Their
application-specific GUI steps do not imply a missing universal parser, automatic
blur/Return, or auto-submit feature. Prefer further representative application
qualification over adding implicit behavior.

**AUTH-03/04/09/10 and WM-01/04/05/06/07/08:** existing implementations and scoped
native/synthetic evidence require their own limits to be retained; this audit
found no comparably clear new API justified ahead of the ranked work. In
particular human-presence presentation does not require challenge solving, and
modal close refusal must never imply document save.

## DATA-03 follow-up

The original ranked finding above described the audited baseline. The additive
`range_end_id` contract now covers bounded, visible, same-inspection list/table
ranges with per-action identity/order and selected-set verification. Actual GTK
MULTIPLE and SINGLE-mode results, sort/filter/recycle cases and retained discovery
failures are in [RANGE-SELECTION.md](RANGE-SELECTION.md). This does not establish
unloaded/virtualized range inference, stable record generations for reused
identities, atomic application interaction, or catalog qualification.

## DATA-07 hard-break follow-up

An explicitly cooperating application can now declare its actual Shift+Enter
hard-break binding. The existing typing tool distinguishes hard breaks from
paragraph LF with exact structure/mark/caret readback in the bounded basic schema.
[Scoped real-provider evidence](OWNED-HARD-BREAKS.md) retains incorrect bindings,
legacy/unsupported refusals and composition boundaries. This does not admit links,
lists, tables, arbitrary schemas or generic rich editors, nor qualify DATA-07.
