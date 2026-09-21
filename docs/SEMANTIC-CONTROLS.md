# Semantic desktop control contract

The isolated AT-SPI worker operates on one previously observed top-level window.
The server owns window/process lifetime checks, activation, serialized access,
60-second element expiry and a hard worker deadline. Public tools accept opaque
`element_id` values; provider paths and identity fingerprints remain private.

## Scope and identity

Inspection uniquely matches accessible top-level bounds to the observed X11
window. A strict GTK4 compatibility path permits an exact title and dimensions
match within the same process when the provider reports a zero-origin top-level.
It still requires uniqueness and complete top-level enumeration. This path reports
`window_mapping: "unique_title_and_size"`, removes node bounds and marks
`bounds_coordinates: "unavailable"`; it must not supply pointer coordinates.
The regular mapping is `screen_bounds`. Public inspection declares usable bounds
as `bounds_coordinate_space: "native_x11_root_pixels"`, not screenshot pixels.

Element identity includes the accessible root/path, process start, role and name.
Public names are limited to 300 characters; a private SHA-256 fingerprint covers
the complete unprotected name, so changes beyond that prefix invalidate a handle.
Names over the 1 MiB UTF-8 identity budget are refused or omitted as unreadable,
not truncated into an identity. The native name getter returns its full value
before this check; the budget bounds encoding/hashing, not the provider reply.
Protected names are redacted without reading their original names.

A provider can reuse a path, role and identical full name for another item without
exposing a generation change. These checks cannot distinguish that reuse. Inspect
again after sorting, filtering or rebuilding a collection; an index is not stable
item identity. Missing providers report `ACCESSIBILITY_UNAVAILABLE`; multiple
matching top-levels are ambiguous. Missing or changed existing targets are stale.

## Observations

`inspect` accepts:

- `limit`: 1..500 returned nodes, default 150.
- `max_depth`: 0..60, default 30; zero returns only the root.
- `filters`: case-insensitive `name`/`role` substrings and required `states`.
  Filtering does not prune descendants.

Responses include availability, visited-node counts, unreadable nodes/branches and
truncation reasons. Traversal visits at most 1600 nodes, bounds queue growth and
has a three-second inspection deadline in addition to the hard worker deadline.
Unreadable nodes or branches make the result incomplete. A reachable provider
with zero filter matches is not an unavailable provider. Nodes expose roles,
states, interfaces, supported actions and available bounds/value metadata. A
filtered or omitted parent need not have a public parent element ID.

`read` accepts `limit` 1..1000000, default 16000. It returns a text prefix, the full
normalized character count, truncation, caret and up to 100 selection ranges.
Public offsets always count **Unicode code points**, not bytes, UTF-16 units or
grapheme clusters. `provider_offset_units`, `provider_text_encoding` and
`selection_source` describe provider normalization. Protected text is refused.

The returned text/count/truncation use the same bounded snapshot. Normalization
reads the complete field: at most two million provider units and one million
returned code points before provider decoding. A smaller public read limit does
not make this a streaming reader. Larger fields produce `VERIFICATION_LIMIT`;
inconsistent or changing provider counts are refused rather than guessed.
Same-length concurrent edits and edits after observation remain possible.

Native EditableText insertion and full-field replacement now apply the same opaque
Hypertext boundary as the clipboard route. Actual embedded objects are refused
before any text mutation, including before deleting a selected range. A provider
that introduces objects during deletion, insertion, or replacement produces
`TEXT_REPRESENTATION_UNSUPPORTED` with an uncertain effect; no second insertion or
automatic retry follows that detection. A literal U+FFFC without an associated
Hypertext link remains ordinary text. Whole-field replacement of preexisting
opaque objects is conservatively refused: no qualified native-provider evidence
currently establishes safe elimination and exact logical plaintext readback.

This guard closes a deterministic provider-contract gap: native insertion formerly
returned verified placeholder-text readback without consulting representation
metadata. The regression uses protocol doubles with actual Hypertext link metadata;
it does not claim a newly qualified live rich-text provider.


## Provider text conventions

Qt uses UTF-16 offsets and insertion lengths, including when the existing text is
ASCII. GTK providers using code-point offsets receive UTF-8 byte insertion lengths.
The worker validates reported counts against text before converting public offsets.

Gecko's ATK text inserts one synthetic U+FEFF after each astral character. The
Gecko-specific decoder validates and removes that padding while preserving actual
U+FEFF characters, and converts UTF-16 offsets. Firefox's advertised EditableText
mutations are known no-ops for the qualified text/password controls, so native
`set`, `insert` and `secret` are refused there. Ordinary public `desktop_type` can
use verified focus/selection, clipboard input and normalized readback instead.
It does not use that fallback for protected input.

Chromium's modern Document selection API avoids broken legacy non-BMP selection
endpoints. The qualified older Electron provider lacks those usable endpoints;
non-BMP selection is refused with `SELECTION_UNVERIFIABLE`. No inverse offset is
guessed. Hypertext containing embedded objects reports its representation and
whether plain-text verification is supported. Public typing refuses an opaque
initial representation; if paste creates one, the outcome is uncertain with
`TEXT_REPRESENTATION_UNSUPPORTED`. Copying and flattening rich text is not an exact
verification substitute. See the provider evidence linked below.

## Mutations

Mutations revalidate identity and require showing plus enabled or sensitive state.
GTK4 can omit enabled on a sensitive control; disabled controls remain refused.
Provider showing state alone is not proof that a table row is inside its viewport.

| Worker operation | Contract |
| --- | --- |
| `set(text)` | Replace editable text and compare complete readback. |
| `insert(text)` | Replace one current selection or insert at the caret, preserving surrounding text. |
| `select(start_offset, end_offset)` | Select a code-point range; equal offsets clear selection and set the caret. |
| `secret(text)` | Replace an observed protected EditableText field without reading its contents; acceptance is dispatched, never value-verified. |
| `focus` | Request focus and verify the current focused state. |
| `value(value)` | Require a finite value inside provider bounds and compare exact numeric readback; rounding is not silently accepted. |
| `check(checked)` / `expand(expanded)` | Idempotently request and verify the desired state using a recognized action. |
| `choose(extend)` | Select an observed option, radio choice or visible table row and verify selection. |
| `invoke(action)` | Dispatch an explicitly reported action; the application outcome is unverified. |

Native text mutation requires usable Text/EditableText capabilities and editable
state. Text must be valid Unicode within the verification budget; LF, tabs,
astral characters and trailing whitespace are preserved. NUL, CR, surrogates,
protected ordinary input and multiple insertion selections are refused. Insertion
rechecks text and range before mutation and verifies deletion before inserting.
Exact text comparison and `caret_verified` are separate postconditions: a provider
may accept text while not supporting placement of the final caret. `accepted`
alone never establishes success.

Public `desktop_type(mode="insert"|"replace")` orchestrates native operations or
the supported focus/selection/clipboard/readback path. Empty replacement clears
a field. Known unsupported native providers are selected before mutation; an
unexpected accepted no-op is not a reason to blindly retry with another backend.
Protected input has no automatic ordinary-field or clipboard fallback.

Focus always requests provider focus before verification. If that request raises,
a fresh focused state can establish focus with `focus_request_supported: false`.
Recognized state-changing action names are matched case-insensitively while
retaining their actual provider index. Missing actions are explicit refusals.

For a TableCell, `choose` selects its **whole row**, checks table/cell identity and
viewport intersection, and reports `selection_scope: "table_row"`. Unavailable
coordinates and offscreen sentinel bounds are refused. `extend=true` preserves
other list/table-row choices. Scroll and inspect again before choosing offscreen
rows. This is not generic pagination, virtualized-item lookup or cell editing.

For editing, enter cell edit mode through an observed action or screenshot input,
then inspect for its editor. The qualified GTK grid omits that visible editor from
AT-SPI. Deliberate GUI paste, explicit commit and fresh committed-cell readback
worked with an independent model oracle; its native edit action did not. These
are separate provider outcomes, not a claim that generic semantic editing works.

Preflight failures have no text mutation effect; errors after possible mutation
and mutating transport timeouts are uncertain. No blind retry or automatic
rollback is safe. Native exception messages are sanitized because they can echo
application contents. These bounded sequences are not atomic transactions and do
not detect pending IME composition or prevent later application/user edits.

## Evidence and remaining limits

Deterministic contract tests include `tests/test_semantic.py` and the provider,
identity and table regressions in `tests/`. The opt-in
[qualification matrix](QUALIFICATION-MATRIX.md) runs isolated live suites with
independent application, file or DOM oracles. Recorded failures remain evidence;
passing one fixture does not qualify every control from that toolkit.

- [GTK3, Qt and GTK4](TOOLKIT-QUALIFICATION.md): concrete selection/caret and missing
  action limitations remain in GTK4.
- [Protected and option controls](PROTECTED-AND-OPTION-CONTROLS.md): acceptance-only
  secret input and supported list/combo/radio behavior.
- [Browser text](BROWSER-TEXT-CONTRACT.md), [Chromium](BROWSER-QUALIFICATION.md),
  [Firefox](FIREFOX-QUALIFICATION.md) and [Electron](ELECTRON-QUALIFICATION.md):
  provider-specific text conventions, rich-text and protected-input gaps.
- [Provider readback review](PROVIDER-TEXT-REVIEW.md): count/snapshot consistency
  and the limits of concurrent-edit detection.
- [Data controls](DATA-CONTROLS.md): viewport selection, sort/filter stale handles,
  lazy children and the actual editable-cell GUI workflow.
- [IME composition](IME-COMPOSITION.md): generic preedit visibility is unknown;
  committed-text verification does not verify a future composition commit.
- [Accessibility lifecycle](LIFECYCLE-QUALIFICATION.md): some existing providers
  fail to re-register after bus loss; restarting user apps is not automatic.

`desktop_invoke(element_id)` selects the sole action from that observed handle. If there are multiple actions, `ACTION_REQUIRED` asks for an exact observed name; zero actions or an unobserved name are refused before the worker. The worker still revalidates the selected name against the live provider. This avoids guessing whether a toolkit calls its button action `click`, `press`, or `activate`; it does not choose between distinct operations or verify application completion.

### Observed list and table ranges

`desktop_choose(element_id, range_end_id=other_id, extend=False)` selects an
inclusive range in either endpoint order. Endpoints must come from one inspection,
one list/table and, for tables, one column. Every intervening item must have been
observed in contiguous provider order and remain enabled and visible. The limits
are 50 range items and 500 selected items. Radios, combo popups, unloaded rows,
missing intermediate observations and duplicate range labels are refused.

The worker checks captured provider/path/name identities, order, window activity,
viewport and the exact selected set before and after each component action.
`extend=False` removes other selections; `True` preserves them. List replacement
uses one verified clear followed by additions; the clear counts as one component
action. Already exact selections dispatch nothing. GTK may omit its
multiple-selection hint even in MULTIPLE mode, so its absence is reported rather
than fabricated. A single-selection provider can accept an initial component and
then fail the requested set: the tool stops with an uncertain error and does not
replay or undo prior changes.

A final `selection_step` receipt counts verified component actions, one possibly
changed component and actions not started. Counts describe historical readbacks,
not current application state or saved data. Lost worker receipts cannot provide
these counts. Inspect after partial failure before deciding the next action.
Provider path/name reuse with identical exposed meaning has no stable application
record-generation proof; rechecks are not atomic against application changes.
See [real GTK range evidence](RANGE-SELECTION.md) for the exercised scope.

Numeric value and check/expand receipts now report the exact provider observation used by their verification predicate. Previously a second read could produce a contradictory receipt (`exact_match: true` for requested 5 alongside `actual_value: 9`, or verified checked=true alongside `checked: false`). Deterministic provider-change regressions cover those cases, unchanged-state no-ops, and failed actions. The receipt describes an observed postcondition; it does not promise that an application cannot change immediately afterward. No mutation is retried. Selection receipts already return the requested offsets paired with `exact_match`, without this additional post-verification provider read; their behavior is unchanged.

Provider numeric metadata must be finite. Inspection retains a control with `value_error: VALUE_UNVERIFIABLE` and omits its numeric block when metadata is invalid or unreadable. Numeric mutations require finite, ordered minimum/maximum bounds; they do not require unused current/increment metadata. Invalid bounds refuse before input; nonfinite or unreadable post-action values produce `VALUE_UNVERIFIABLE` with uncertain effect and no automatic retry. Native insertion character counts now come from the same string used for exact verification, including mismatch results. Verified caret offsets likewise describe the separately observed caret, not a later reread or an atomic guarantee across both observations.

### Selection verification scope

Successful `desktop_choose` results retain `effect: "verified"` and the existing provider fields, and add `verification_scope: "selection"` plus `next_step`. This also applies when the requested selection was already present. Verification establishes the selection state only; it does not establish opening, applying, or executing the selected item. Selection-only tasks can stop there. For other tasks, check the application effect first, since some controls apply changes on selection. If the effect is absent, use an advertised activation action or Apply/Open control, then verify the application result. Luda does not automatically activate every selection. Uncertain or failed selection results do not acquire a verified selection scope.

See the [tool regression and fresh-agent evidence](../tests/evidence/selection-feedback/README.md) for observed outcomes and limits.
