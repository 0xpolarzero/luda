---
name: luda
description: Operate native applications and desktop dialogs inside a Silo Linux X11 sandbox using the silo-desktop tools. Use for visible desktop interaction; browser DOM tasks can use an available browser tool attached to the same guest.
---

Use `desktop_doctor` when attaching or recovering a session. If it fails, the guest launcher/dependencies need repair; do not guess DISPLAY or attach to a different user's session.

List windows and activate the intended window. `desktop_observe` supplies the screenshot, window IDs and snapshot ID. Pointer coordinates refer to that returned image, not the native screen resolution. Snapshots expire after 15 seconds and are invalid after window layout/focus changes. Observe again on `STALE_OBSERVATION`.

Prefer `desktop_inspect` and semantic element actions when available. Element IDs expire after 60 seconds and belong to one server. Reinspect on `STALE_TARGET`; never substitute a similar-looking element without checking its identity. A partial or empty accessibility tree is not proof that the app has no UI; use the screenshot.

For text:
- `desktop_set_text` replaces the entire editable element and checks exact readback. Empty text clears it. This is distinct from insertion at the caret.
- `desktop_enter_text` pastes at the caret through CLIPBOARD. Choose the app's shortcut explicitly: commonly ctrl_v for editors/browsers, ctrl_shift_v for terminals. Shift+Insert can use PRIMARY instead in some terminals. This tool only verifies clipboard contents; read the destination or observe the resulting UI.
- LF, tabs, blank lines and Unicode are preserved by the tool. CR, NUL and other control characters are rejected rather than silently changed.
- Use `desktop_press_keys` for deliberate Tab, Return, shortcuts and submission. Pasted newlines can execute commands in a terminal. Inspect multiline-paste dialogs and follow the user's intended action; the tool does not accept them automatically.

`effect=verified` names the specific condition checked. `dispatched` means input was sent. `uncertain` means an effect may already have occurred: inspect before retrying, especially for Save, Send, Delete or submission. Do not turn a timeout into an automatic repeated click.

The tool serializes its own clients but does not exclude a human using the guest viewer. Unexpected focus/layout changes require a new observation. Clipboard contents are replaced and are not restored. Protected fields, cross-window drag, Wayland and browser DOM automation are outside this version's implemented support.
