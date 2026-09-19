# Explicit protected input and option selection

The parent server supplies the observed element token, verifies that its scoped
window is active and enforces the normal mutation lease. The worker retains stale
identity, disabled and hidden-target checks for these operations.

## `secret(text)`

This operation is intentionally separate from ordinary text editing. It requires
an already observed protected field, EditableText and an editable state. It never
falls back to a normal field, clipboard or simulated typing. It replaces the
protected contents through the provider's EditableText interface.

The response reports only `accepted`, `effect` and a verification explanation.
Accepted input is **dispatched**, never a verified secret value. No Text interface
read occurs and neither the input nor its length is returned. Provider exceptions
are replaced with a fixed text-free error because providers can echo arguments in
exceptions. Rejection/timeout does not prove that no mutation occurred.

Ordinary read, set, insert and selection operations continue refusing protected
fields. Invalid Unicode, NUL, CR and oversized input are refused without echoing
contents. Authentication submission remains a separate explicit action.

## `choose(extend=false)`

The target is the observed option itself, not an arbitrary numeric child index or
unobserved text match. By default it establishes an exclusive choice;
`extend=true` preserves other selected list options. Already satisfied choices are
idempotent. Three provider paths are supported:

- **Selection container:** verify the direct child identity, select it, and remove
  other actual selected children when exclusive. Deselect selected-child indices
  in reverse order, verifying identities, rather than assuming child and selected
  indices mean the same thing. GTK ListBox omits `multiselectable` despite allowing
  multiple selection, so normalization uses actual selected children.
- **Selectable list-item actions:** Qt QListWidget exposes Toggle/selected on
  items instead of Selection on the parent. Only advertised, unambiguous Toggle
  actions are used. All affected siblings are bounded and selected states verified.
- **Radio:** request checked=true via the existing idempotent checked operation.
  Radio choices do not support extend.

Normalization is bounded to 500 options and is not an atomic application
transaction. Unexpected provider failures or concurrent changes produce uncertain
outcomes; do not blindly retry.

**Combo options require commitment rather than highlight.** An observed GTK combo
popup option is activated through its advertised action, then the enclosing
combo's selected child identity is verified. Generic menu commands require
`invoke`, not `choose`. Qt combo options lacking a verifiable semantic commit path
return UNSUPPORTED_ACTION before mutation; the screenshot/keyboard popup workflow
remains available through the desktop tools. Hidden/collapsed options are not
silently selected.

## Independent evidence

Run under the full desktop lease:

```bash
flock /tmp/luda-live-tests.lock .venv/bin/luda-session -- \
  "$PWD/.venv/bin/python" "$PWD/tests/live_controls.py"
flock /tmp/luda-live-tests.lock .venv/bin/luda-session -- \
  "$PWD/.venv/bin/python" "$PWD/tests/live_combo.py"
```

`live_controls.py` passed 32 checks across GTK3 and Qt5: exact independent hashes
for synthetic protected inputs (ASCII, Unicode and empty), no plaintext response,
nonprotected/disabled-target refusal, ordinary protected read/set refusal,
exclusive/additive/idempotent list choices, and radio changes/idempotency.

The password fixture emits only a SHA-256 hash, never plaintext protected contents.
These are synthetic test values, not credentials. Toolkit object state independently
supplies list/radio choices. `live_combo.py` confirms GTK combo value changes to the
chosen option; Qt explicitly reports unsupported rather than claiming highlight
committed the choice. Results are written to ignored `artifacts/controls` and
`artifacts/combo`.

Deterministic unit tests additionally cover provider exception redaction, absent
EditableText, malformed secrets, false deselection success, stale option indices,
disabled containers and missing selection interfaces. This qualification covers
the tested GTK3/Qt5 controls, not all custom password widgets or virtualized lists.
