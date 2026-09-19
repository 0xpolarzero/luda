# Qt5 and GTK4 qualification

`tests/live_toolkits.py` launches only synthetic fixtures, queries their windows
through Luda and compares effects against state saved by the actual toolkit
objects. It owns and closes its applications. Run with the entire desktop lease:

```bash
mkdir -p artifacts/toolkits
chmod a+rwx artifacts/toolkits
flock /tmp/luda-live-tests.lock .venv/bin/luda-session -- \
  "$PWD/.venv/bin/python" "$PWD/tests/live_toolkits.py"
```

The desktop account must be able to write `artifacts/toolkits`. Dependencies are
distro `python3-pyqt5`, `gir1.2-gtk-4.0` and the existing Luda desktop prerequisites.
No network, vendor key or user data is needed. The JSON report distinguishes
`supported`, `unsupported` and `failed`; failures cause a nonzero exit. A dispatched
action counts as supported only if the independently persisted application state
confirms its requested effect. This does not upgrade the tool response itself to
verified.

## Initial result against worker feba389

Tested on the current Ubuntu 24.04 ARM64 XFCE/KasmVNC guest. Of 23 recorded
observations, 17 were supported, 3 unsupported and 3 failed. This is evidence of
incomplete cross-toolkit coverage, not a passing release gate.

Qt5 passed scoped accessibility inspection, verified focus, exact full-field
replacement including Unicode/multiline/tabs/empty text, numeric value changes,
password redaction/read refusal, and modal opening, scoped inspection and closing.

Qt5 exposed two concrete worker defects:

1. The bounded initial text read requests an end offset beyond the text length.
   GTK3 clamps this, but Qt5 returns an empty string. Consequently selection and
   insertion cannot use the actual field content. The worker must read a validated
   provider character count and request a valid end offset.
2. Qt checkboxes expose `Toggle` and `SetFocus`; the worker recognizes only lowercase
   `toggle`, `click`, `activate`. Semantic action matching needs normalization while
   preserving the original provider action index.

GTK4 exposes Text, EditableText, Value and accessible modal buttons, but the worker
cannot safely map its top-level using screen rectangles: the fixture reports
`(0,0,620,480)` while its actual X11 client is `(5,56,620,480)`. Descendants also
report zero origins. Accessible bounds must not be silently interpreted as screen
coordinates. Enabled widgets report `sensitive` without `enabled`. The checkbox
reports no action. These are independent compatibility issues; merely relaxing
window matching would not establish functional GTK4 support.

The harness saves failed-scope diagnostics for its own PID only, permitting review
of actual provider states/interfaces/geometry. It does not enumerate or save other
applications' accessibility trees.

Results are retained under ignored `artifacts/toolkits/`: `results.json`, per-toolkit
`inspect.json`, fixture state/logs, and `raw-scope.json` when mapping fails. GTK4
operations blocked by window mapping are not counted as passing or assumed
supported. Subsequent fixes require a fresh run and an updated evidence section.

## Retest after compatibility fixes

The final retest recorded **Qt5: 29 supported, zero failures**. GTK4 recorded
**21 supported, 2 unsupported, 3 provider failures and 3 blocked dependent cases**.
The suite intentionally remains nonzero because GTK4 selection/caret support is
incomplete. GTK3 regressions also passed: 35 semantic and 31 baseline live checks;
33 unit tests passed across the branch.

Qt now normalizes its UTF-16 offsets to the public code-point contract, including
selection after astral characters and caret placement after inserting emoji into
initially ASCII text. Qt's declared application toolkit also selects UTF-16 units
for the InsertText length argument. Direct fixture probes established that using
UTF-8 byte length here pads or corrupts inserted text; independent Qt object
readback caught the discrepancy even when AT-SPI returned a truncated string.
GTK retains its UTF-8 insertion length convention. `read` exposes
`provider_offset_units` diagnostically while all public offsets remain code points.

GTK4 mapping now permits an exact unique top-level title plus client dimensions
when the provider reports zero-origin extents. Ambiguous names/sizes and incomplete
top-level enumeration are refused. The parent supplies `window_title`; responses
report `window_mapping: "unique_title_and_size"` and
`bounds_coordinates: "unavailable"`. All such node bounds are removed, so clients
cannot accidentally click zero-origin accessibility geometry. Valid native X11
window/screenshot coordinates remain available through the desktop layer.

GTK4's sensitive/showing widgets are operable even when `enabled` is omitted;
independent disabled-button tests still reject mutations. Its passing cases include
full text replacement, exact Unicode insertion at the current caret, reading,
already-focused verification, Value changes, protected-field refusal and scoped
modal opening/closing. Checkbox mutation has no advertised action and is explicitly
unsupported. Selection and caret-setting APIs raise provider errors. Dependent
insertion cases are marked `blocked` and not attempted; they do not misrepresent
otherwise-working insertion. No speculative keyboard fallback was added.

The worker does not discard a verified text result if optional caret positioning
is unsupported: `exact_match` and `caret_verified` remain separate. It first checks
whether the provider already placed the caret correctly, avoiding an unnecessary
unsupported operation.

The test harness provides `window_title` to the worker for branches whose parent
Desktop adapter has not yet integrated that request field. Application effects
use bounded independent-oracle polling because action acceptance can precede an
asynchronous modal appearing. Accessible names are not assumed unique: the fixture
harness selects the first matching control rather than overwriting it with its
child label.
