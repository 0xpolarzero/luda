# Newlines in single-line fields

`tests/live_single_line.py` sends the same synthetic Japanese/Hebrew/emoji text
with two LF characters to real GTK Entry, Qt QLineEdit and Chromium HTML input.
Public Desktop operations drive input; independent widget or DOM readback records
actual storage. Playwright only creates the disposable page and reads its state.

```sh
.venv/bin/python scripts/qualification_matrix.py --suites single-line --executable /path/to/chromium
```

The final ordinary-UID ARM64 run passed all three cases in 4.937 seconds:

| Field | Actual behavior | Luda result |
|---|---|---|
| GTK Entry | Stores the exact 27-code-point string, including both LF characters | `verified`, exact match |
| Qt QLineEdit | Stores the same exact string | `verified`, exact match |
| Chromium153 HTML input | Pasted line boundaries become spaces and trailing LF disappears | `TEXT_MISMATCH`, `effect: uncertain`; no submission |

A single-line widget's storage semantics do not necessarily prohibit LF. The native
results establish stored characters, not multiline visual presentation. Chromium's
transformation is detected instead of silently trimming the expectation or claiming
success; no automatic second insertion follows the error.

Evidence: `artifacts/qualification-matrix/run-1789875628994208552`, unchanged
source fingerprint `6f29e4cc1318e9bfcc235451d3b9508e9252a49968b65fca4ceb6397713d52ce`, no owned survivors.
GTK/Qt fixture state now reports each actual runtime widget class independently.
Qt omits the `single-line` AX state in this provider; an initial test incorrectly
required it even though both widgets stored exact text. That failed probe remains
in `run-1789875356914810839`, followed by the corrected native-only pass
`run-1789875399247986692`.

Browser setup probes are preserved too: the first omitted Chromium's native
accessibility opt-in; later unfiltered inspection exhausted the 150-result budget
in browser chrome before returning the field. The final fixture enables the bridge
and uses public name-filtered inspection. None of those harness failures was
reported as a typing defect. Their runs are `run-1789875490326214944`,
`run-1789875535598536382`, and `run-1789875575218871985`.

This is scoped EDIT-05 evidence for these three providers. It does not qualify
all validators, max-length fields, IME composition, password widgets or application
commit behavior. All catalog qualification statuses remain unchanged.
