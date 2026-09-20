# Outcomes, waits, and recovery

## Interpret the receipt

| Effect | Meaning and next decision |
|---|---|
| `none` | This operation reports no effect; use its error/availability reason to choose a supported next step. |
| `dispatched` | Input/action was sent; check the application outcome. |
| `verified` | The specifically named postcondition was observed; this is neither future stability nor save/commit unless explicitly established. |
| `uncertain` | Input may already have affected the application; inspect current state before any retry or alternate transport. |

Read additional progress and verification fields, not only success/error status. Some steps can be verified while later steps remain uncertain. Historical progress is not a replay instruction. State can race between preflight and dispatch because a human or application can act concurrently.

## Wait for a specific condition

`desktop_wait` is observation only; it never repeats input. Timeout is 0–10 seconds. Provide arguments only for the selected condition:

| Condition | Required arguments |
|---|---|
| `window_present`, `window_absent`, `window_active` | `window_id` |
| `text_equals`, `text_contains` | `element_id`, `text` |
| `element_present`, `element_absent` | `window_id` plus at least one `name`, `role`, or `states` filter |
| `pixels_stable` | `window_id`; optional `stable_for` (0.1–10 seconds, no greater than timeout) |

```python
desktop_wait(condition="text_equals", element_id="<entry_id>", text="Expected", timeout=5)
desktop_wait(condition="element_present", window_id="<window_id>", name="Saved", timeout=5)
```

For a not-yet-known window title, poll `desktop_windows(query="...")` to discover its ID; do not pass a title as `text` to a window wait. Element conditions search freshly inspected **native accessibility nodes**; they are not DOM selectors or owned-browser-field waits. Absence requires complete coverage, so unavailable/truncated accessibility cannot prove a control disappeared. `pixels_stable` samples the client rectangle, not general application idleness.

## Recovery by cause

| Situation | Response |
|---|---|
| `STALE_OBSERVATION` | Observe again, identify the target in current content, use the new snapshot. |
| `STALE_TARGET` | Reinspect and match current identity/context before using a new element ID. |
| Focus/layout changed or target covered | Find/activate the intended window, inspect/observe again; account for possible already-delivered input. |
| Accessibility unsupported/incomplete | Use screenshot-grounded input where it can satisfy the task; disclose verification limits. |
| `INPUT_HELD` | Wait for existing human-held input to be released; do not release unrelated input. |
| `UNSUPPORTED_KEYMAP` | Use semantic text tools or an observed supported action; do not change the keyboard layout automatically. |
| `SESSION_BLOCKED` | Keep observation available; let the human resume the intended desktop, then observe again. |
| Missing optional dependency/provider | Continue with independent available capabilities or arrange explicit installation; do not call an unavailable feature repeatedly. |
| Text boundary/representation refusal | Preserve requested range/content. Choose another deliberate workflow only after checking whether any effect occurred. |
| Uncertain Save/Send/Delete/launch/edit | Inspect current application state before retrying or switching transports. |

## Timeout, cancellation, and owned input cleanup

A client-side timeout may not send MCP cancellation. Even a cancellation acknowledgment can precede worker cleanup. Call `desktop_status()` to inspect recovery and recent operation outcomes; it omits typed text/screenshots. Wait until recovery is complete and inspect application effects before another mutation.

If interrupted supervised input cleanup remains blocked, call `desktop_recover_input()`. It retries only **owned cleanup**, using the original session; it does not replay keys/clicks, resume a paused display, or establish application success. Read `pending_count`, `recovering`, and recovery proofs. `BUSY` means an operation is still running. Unproven ownership/cleanup stays blocked. It works while paused.

Do not kill unrelated applications or release arbitrary keys/buttons as a recovery shortcut. If recovery proves the original X server was replaced, reconnect to the intended new session and obtain fresh observations.

## Pause and restart

`desktop_control(action="status")` reports pause state. `pause` interrupts cooperating Luda mutation at the next checkpoint; already-delivered input is not undone and external input programs are unaffected. Observation remains available. `resume` requires the user's instruction when they requested the pause; healthy doctor results do not provide that authority.

After the desktop restarts, `desktop_reconnect()` can attach this connection to a validated session of the same account. Reconnect currently accepts XFCE sessions only, including when a PID is supplied. If multiple candidates exist, select the intended reported `session_pid`. For another session manager, restart the MCP connection through the correctly configured launcher/environment instead. Do not guess DISPLAY or attach another account.

Failed validation preserves the old backend. Successful reconnect invalidates all prior window, element, and screenshot handles; observe again. It preserves the selected display's pause state and never restarts apps or replays input. It closes temporary owned browsers and loses their unsaved data. An unconfirmed browser cleanup can leave the overall result uncertain even when attachment succeeded.

## Diagnostics and reports

Use `desktop_doctor` for actual session access and per-capability availability. Distinguish:

- a product defect (supported behavior fails despite valid preconditions),
- a missing prerequisite or unsupported environment/provider,
- a test/client problem (wrong coordinates, stale IDs, incorrect expected state, or missing cancellation).

Do not broaden installation or architecture to hide an unsupported case. The server reports its driver and bundled skill/tool identities; those do not prove which skill files the agent actually loaded.

`desktop_report()` returns sanitized environment/version/health information and up to 32 recent operation outcomes from this MCP process. It excludes desktop content, paths, exception messages, and action arguments. It does not save/upload files or replay actions. For a requested bug report, supply synthetic reproduction steps separately and save/share only as authorized. `luda report` starts a new process and cannot recover the connected server's history.
