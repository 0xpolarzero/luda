---
name: luda
description: Operate native applications and desktop dialogs inside a Silo Linux X11 sandbox using the Luda tools. Use for visible desktop interaction; browser DOM tasks can use an available browser tool attached to the same guest.
---

Use `desktop_doctor` when attaching or recovering a session. If it fails, the guest launcher/dependencies need repair; do not guess DISPLAY or attach to a different user's session.

List windows and activate the intended window. `desktop_observe` supplies the screenshot, window IDs and snapshot ID. Pointer coordinates refer to that returned image, not the native screen resolution. Snapshots expire after 15 seconds and are invalid after window layout/focus changes. Observe again on `STALE_OBSERVATION`. Owned menus and submenus use the same window ID and pointer tools; covered targets are refused.

Prefer `desktop_inspect` and semantic element actions when available. Element IDs expire after 60 seconds and belong to one server. Reinspect on `STALE_TARGET`; never substitute a similar-looking element without checking its identity. A partial or empty accessibility tree is not proof that the app has no UI; use the screenshot.

For text:
- `desktop_type` inserts at the caret or replaces the selection and verifies readback. Use `mode="replace"` to replace the whole field; empty text in replace mode clears it. This is distinct from insertion at the caret.
- `desktop_paste` pastes at the caret through CLIPBOARD. The shortcut is selected from the window class; override it only for known app-specific bindings. Shift+Insert can use PRIMARY instead in some terminals. This tool only verifies clipboard contents; read the destination or observe the resulting UI.
- LF, tabs, blank lines and Unicode are preserved by the tool. CR, NUL and other control characters are rejected rather than silently changed.
- Use `desktop_type_secret` only for an observed protected field. It does not read or verify the secret value, and never submits it. Ordinary typing and reading refuse protected fields.
- Use `desktop_press_keys` for deliberate Tab, Return, shortcuts and submission. Pasted newlines can execute commands in a terminal. Inspect multiline-paste dialogs and follow the user's intended action; the tool does not accept them automatically.

`effect=verified` names the specific condition checked. `dispatched` means input was sent. `uncertain` means an effect may already have occurred: inspect before retrying, especially for Save, Send, Delete or submission. Do not turn a timeout into an automatic repeated click.

Use `desktop_choose` on an observed option for list/radio/combo selection; `extend=true` preserves other list choices. Open collapsed options and inspect first. Use `desktop_select` for explicit selection/caret placement, and `desktop_set_checked`, `desktop_set_expanded`, or `desktop_set_value` for desired states. These avoid blind toggles. `desktop_window` manages window state; `desktop_drag_to` transfers between observed windows. Verify application drop effects.

Use `desktop_wait` for an observable text/window condition. It never retries input. After cancellation, `desktop_status` reports recovery and recent outcomes without retaining typed text. A client-side timeout may not send MCP cancellation; even a cancellation acknowledgment can precede worker cleanup. Wait for recovery and inspect effects before another mutation.

`desktop_control` pauses or resumes mutations across cooperating Luda clients on this display; observations remain available. Never resume a user-requested pause without their instruction.

The tool serializes its own clients but does not exclude a human using the guest viewer. Unexpected focus/layout changes require a new observation. Clipboard contents are replaced and are not restored. Wayland and browser DOM automation are outside this version's implemented support.
