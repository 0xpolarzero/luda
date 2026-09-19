# Semantic desktop control contract

The isolated AT-SPI worker operates on one previously observed top-level window.
Requests contain `pid`, Linux process `start` identity and `op`. Element requests
add the previously observed `target` (root path, element path, role and name).
The parent server owns token expiry, window activation, serialized access and a
hard subprocess deadline. Paths are internal; public tools should use opaque IDs.

## Observations

`inspect` requires `bounds` and `frame_bounds` and uniquely matches these to an
accessible top-level before traversing. Options:

- `limit`: integer 1..500, default 150 returned nodes.
- `max_depth`: integer 0..60, default 30. Zero returns only the root.
- `filters`: optional `name` and `role` case-insensitive substrings, plus `states`
  as a list of required state strings. Filtering does not prune matching descendants.

Responses include `nodes`, `available`, `visited_nodes`, `max_depth`,
`unreadable_nodes`, `unreadable_branches`, and `truncated`. `truncation` separates
result/time limits, depth pruning, traversal budget pruning and unreadable
branches. `available` means the scoped accessibility provider was reachable;
zero filter matches does not mean accessibility is unavailable. Traversal visits
at most 1600 nodes, bounds queue growth and uses a three-second inspection deadline
in addition to the parent's hard deadline. Slow provider calls can reach the hard
deadline first. Unreadable branches make the result incomplete.

Each node exposes roles, states, supported interfaces, bounds, action names and,
when supported, numeric `value` limits/increment/current value. Inspection adds
`parent_path` so the server can remap it to a returned parent element ID. A filtered
or truncated parent need not be present. Password names are redacted and values
are omitted.

`read` accepts `limit` 1..1000000 (default 16000). It returns text, full reported
character count, truncation, caret offset, up to 100 selection ranges, and explicit
`offset_units: "Unicode code points"`. These are code points, not UTF-8 bytes or
grapheme clusters. Protected fields are rejected before text access.

## Mutations

All mutations reject disabled or non-showing controls and stale identity. Errors
before a mutation are refusals; unexpected provider exceptions/timeouts during a
mutation must be reported by the server as an uncertain effect. Never blindly
retry an uncertain mutation.

| Worker operation | Arguments | Contract |
| --- | --- | --- |
| `set` | `text` | Replace the complete editable text and compare full readback. Parent validates text first. |
| `insert` | `text` | Replace the current single selection, or insert at the caret, preserving all surrounding text. |
| `select` | `start_offset`, `end_offset` | Select a code-point range; equal offsets clear selection and set the caret. |
| `focus` | none | Request focus, then verify the element's focused state. |
| `value` | finite numeric `value` | Reject values outside provider minimum/maximum, set and compare exact numeric readback. |
| `check` | boolean `checked` | Idempotently request checked state via a recognized action and verify state. |
| `expand` | boolean `expanded` | Idempotently request expansion via a recognized action and verify state. |
| `invoke` | observed `action` | Dispatch an explicitly reported action. Application outcome remains unverified. |

`insert` requires both Text and EditableText and an editable state. It accepts
valid Unicode up to one million code points, including LF, tabs and trailing
whitespace. NUL, CR, surrogates, protected fields and multiple selections are
rejected. The resulting field must remain within the same verification budget.
Before mutation, the worker rereads text and selection/caret to catch concurrent
changes. Selection deletion is verified before insertion proceeds. UTF-8 byte
length is passed to AT-SPI InsertText; offsets remain code points.

Results include `effect`, `accepted`, `exact_match`, expected/actual character
counts, replaced/inserted character counts, `caret_verified` and `caret_offset`.
After exact text readback the worker clears selection and places the caret after
the inserted text. `exact_match` verifies text; `caret_verified` separately reports
the caret postcondition. A provider can accept a request without applying it, so
`accepted` alone never establishes success.

Insertion is a bounded sequence of provider calls, not an atomic transaction.
Human/application edits can race after the last precondition check. A partial
mutation is reported as uncertain and is not automatically rolled back, which
could overwrite another edit. The worker does not synthesize unsupported semantic
operations with arbitrary keystrokes. Callers can explicitly choose a screenshot/
keyboard workflow instead.

## Evidence and limits

Run deterministic fault tests:

```bash
.venv/bin/python -m unittest discover -s tests -p test_semantic.py -v
```

Run real GTK tests as the desktop user while holding the shared display lock:

```bash
flock /tmp/luda-live-tests.lock .venv/bin/luda-session -- \
  "$PWD/.venv/bin/python" "$PWD/tests/live_semantic.py"
```

The 35 live assertions independently read state persisted by a GTK fixture,
covering exact insertion/selection/caret, Unicode, multiline, tabs, numeric values,
idempotent check/expansion, protected and hidden refusal, invalid inputs and scoped
filters/depth. The 16 unit tests include provider false success, rejected deletion,
concurrent text/caret changes, multiple selections and invalid input matrices.
Outputs go to ignored `artifacts/semantic/`; they contain synthetic fixture text.

This evidence qualifies those GTK controls on the current X11 guest. It does not
qualify arbitrary Chromium/Electron, Qt, custom canvases, rich text, IME composition,
virtualized trees, multi-selection editors or AT-SPI providers with different
semantics. Unsupported interfaces produce explicit refusals, not claimed support.
