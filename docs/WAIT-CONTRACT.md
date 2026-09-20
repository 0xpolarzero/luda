# Condition wait semantics

`desktop_wait` preserves window presence/absence/focus and complete-text equality/containment conditions. It also supports:

- `element_present`: requires a window ID and at least one meaningful name/role substring or required-state filter. Each poll obtains a fresh tree and returns the observed element IDs when a match appears. Presence in a partial tree is valid evidence for the returned nodes and is labelled partial.
- `element_absent`: uses the same filters but requires an available, complete, readable tree. Truncated traversal or missing provider coverage produces `VERIFICATION_LIMIT`, never a successful absence claim.
- `pixels_stable`: requires a window ID and `stable_for` of at least 0.1 seconds, no larger than the timeout. It compares sampled returned-screenshot pixels in the target client rectangle. It is explicitly not application idleness or proof that a save/network operation completed.

The wait has its own bounded deadline and inherits caller cancellation and cooperative pause guards. Condition timeout returns `matched=false`; parent cancellation or provider errors remain errors. Pixel stability currently requires the client rectangle to fit entirely inside the desktop image. Changing layout/focus resets stability, and other display errors are preserved.

`tests/test_condition_waits.py` covers filter rejection, partial/unavailable absence, new element identities, cancellation/guard inheritance, changing pixels and stable-interval requirements. `tests/live_waits.py` uses a GTK application that creates/destroys its own delayed control and continuously changes a visible frame counter. A separate atomic state file verifies that a control actually appeared/disappeared and that animation actually ran/stopped. No test treats an echo of its input parameters as the application oracle.

Run the live suite in an isolated Xvfb/XFWM4/session-D-Bus desktop, or hold `/tmp/luda-live-tests.lock` for the entire run against `:1`. Results go to a fresh `artifacts/waits/run-*/results.json` directory (or beneath the isolated runner’s `LUDA_TEST_ARTIFACT_ROOT`).
