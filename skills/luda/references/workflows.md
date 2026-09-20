# Task workflows

These are decision patterns, not fixed scripts. Use existing user authorization; do not add external submissions, content changes, or destructive choices merely to complete a pattern.

## Open or find an application/document

1. List windows and identify an existing relevant instance.
2. If launching is needed, call `desktop_applications(query="editor")` and use a returned `application_id` with `desktop_launch`.
3. To open a requested file, supply `files_or_uris=["/absolute/existing/file"]` when the returned application supports it. Paths refer to the **Linux desktop machine**, not the agent's host or a different machine.
4. Inspect the returned window candidates or enumerate windows. `wait_timeout` (0–3 seconds, default 1) bounds candidate observation; it does not prove document readiness. A singleton app can reuse an existing window without an attributable new candidate. Do not launch again just because the candidate list is empty.
5. Activate the intended window and check the document/title/content before editing.

Luda's desktop API is not a general filesystem or shell API. Use separately available file/shell tools when the user's task calls for them; do not invent a Luda file-transfer or command-execution tool.

## Edit and save a document

Read/inspect the intended editor and choose fragment insertion, selected-range replacement, or whole-field replacement according to the task. Verify the resulting text. If exact plain-text representation is unavailable, use an application-specific outcome check and state that limit.

For saving, invoke the observed Save action or the application's known shortcut. Handle any Save As dialog as a separate window/control context. Verify the filename and directory on the Linux machine, then perform the intended save. A completed shortcut, vanished dialog, or stable pixels alone does not prove the file was durably written. Use an application status/readback or, when available and appropriate, independent file contents to establish the requested outcome.

If a save reports uncertain delivery or times out, inspect dialogs and file/application state before repeating it. When closing reveals unsaved changes, choose save/discard/cancel according to the user's actual intent; do not automatically discard to make close succeed.

## Complete a form

Inspect controls, set ordinary fields with semantic text tools, use desired-state operations for checkboxes/numeric controls, and choose actual options for combos/radio groups. Autocomplete fields may need a suggestion selected after typing. Reinspect dependent fields that appear or change when earlier values change.

Read relevant values before the requested final action. Use secret entry only for an observed supported protected field; it does not submit. Invoke Submit/Send only when included in the task's authorization. Confirm the application outcome (receipt, new record, success page, or validation error), not merely button dispatch. On uncertain submission, look for an existing result before retrying.

## File chooser, overwrite, permission, and other dialogs

Discover the actual dialog in windows/accessibility or the screenshot; do not assume focus remained in the original window. Use its observed controls and paths. Overwrite, permissions, authentication, and unsaved-document choices are distinct application actions; follow the requested intent and verify the outcome.

Luda does not automatically grant permissions, authenticate, unlock a desktop, dismiss all dialogs, or classify every privileged prompt. A registered lock/screensaver produces `SESSION_BLOCKED`; let the intended session be resumed by the human and observe again. An unrecognized dialog or input grab can still prevent interaction even without that signal.

For menus/popups, use their observed owner window and screenshot coordinates. For a separately listed modal window, use that window's identity. Do not blindly send Escape to dismiss an unknown dialog: it can cancel composition, abandon an operation, or close the wrong interface.

## Browser use

Existing browsers remain ordinary desktop applications: operate their visible UI and native accessibility. Opening a new tab, navigating via the address bar, or following a link changes content; reacquire target controls afterward. No DOM access to an existing profile is implied.

If the task specifically fits a disposable fresh browser and the optional provider is installed, see [optional capabilities](optional.md). Its ordinary field tools improve exact text/selection handling but do not provide arbitrary script execution, automatic downloads, or universal website support. Preserve needed data outside its temporary profile before disconnect/reconnect.

## Drag/drop and long operations

Ground source/destination in one fresh screenshot and verify both application outcomes after a drag. The dispatch receipt does not prove a copy, move, upload, or drop was accepted.

For a slow operation, identify a real completion signal: accessible status text, a progress dialog disappearing with sufficient coverage, or a known result window. Use bounded `desktop_wait`; repeat observation, not the triggering action, if more time is justified. Pixel stability means only sampled pixels stopped changing. It cannot establish a completed transfer, download, save, or idle application.

## Report what happened

State the user-visible outcome and any unresolved verification limit. Distinguish “text read back correctly” from “document saved,” “input dispatched” from “form submitted,” and “provider unsupported” from “application has no controls.” If an operation may have partially happened, report the observed current state and stop repeating it blindly.
