# Text and keyboard

## Choose the transport

| Need | Preferred tool | What is established |
|---|---|---|
| Literal editable text | `desktop_type(element_id, text, mode="insert")` | Exact readback where supported |
| Replace the whole field | `desktop_type(element_id, text, mode="replace")` | Entire field replaced; surrounding old content is removed |
| Read text without changing it | `desktop_read_text(element_id, limit=16000)` | Accessible logical text and representation metadata |
| Caret/selection | `desktop_select(element_id, start_offset, end_offset)` | Observed range/caret |
| Keyboard shortcut or navigation | `desktop_press_keys(window_id, chord, count=1)` | Key dispatch |
| GUI field without usable semantic editing | `desktop_paste(window_id, text)` | Clipboard contents, not destination text |
| Observed password field | `desktop_type_secret(element_id, text)` | Dispatch only; no secret readback or submission |

Literal text should not be split into simulated keystrokes. The text tools preserve Unicode, LF, tabs, blank lines, and trailing LF within supported field types. CR, NUL, and other unsupported control characters are rejected, not silently normalized. A single-line field can reject multiline/tab text; inspect its metadata.

## Read, select, and edit

```python
desktop_read_text(element_id="<entry_id>")
desktop_type(element_id="<entry_id>", text="First line\n\nSecond line\t✓\n", mode="replace")
```

Empty text with `mode="replace"` clears the field. Default `insert` adds at the caret or replaces the current selection. Do not use whole-field replacement when the task is to amend a fragment.

Offsets count **Unicode code points**, not UTF-8 bytes, UTF-16 units, or visually perceived characters. For `A😀B`, the emoji occupies offsets 1 to 2. Combining sequences and joined emoji contain multiple code points; some browser-native operations refuse boundaries inside one grapheme rather than expanding the selection.

```python
desktop_focus_element(element_id="<entry_id>")
desktop_select(element_id="<entry_id>", start_offset=1, end_offset=2)
desktop_type(element_id="<entry_id>", text="X")
```

Use offsets from the actual current text, not this example. Equal start/end places a caret. Owned-browser fields require explicit focus before selection. Re-read changed text before computing later offsets.

`desktop_read_text` preserves whitespace. Its `limit` counts code points (maximum 1,000,000); check truncation rather than assuming returned text is complete. The provider reads a bounded full field internally, so lowering the output limit does not enable streaming arbitrary large documents. Inspect `plain_text_verification_supported`: opaque embedded objects can prevent exact plain-text verification. `TEXT_REPRESENTATION_UNSUPPORTED` is not permission to repeat a possibly delivered edit through another transport.

## Verification and application commit

A verified text operation reports an observed value, not persistence. An application can change it immediately afterward. Text/caret verification can be distinct, and typing does not guarantee keyboard-event handlers, autocomplete selection, formatting, or save completion.

- If an autocomplete choice is required, observe suggestions and choose the intended option; matching literal text does not prove that choice.
- For an explicit commit, use the observed control, intended shortcut, or deliberate focus change and read the resulting state. Do not append Return to all text edits.
- Undo grouping is application-defined. One replacement can require multiple undo operations; inspect after each deliberate undo instead of assuming one restores everything.
- For exact formatting or embedded-content edits, use the application's actual controls and an appropriate outcome check. Core plain-text verification does not establish rich document structure.

## Clipboard fallback and terminals

First focus the intended field using an observed action. Then:

```python
desktop_paste(window_id="<window_id>", text="literal text")
```

Luda chooses a common paste shortcut from the window class. Override with `shortcut="ctrl_v"`, `"ctrl_shift_v"`, or `"shift_insert"` only when the application's actual binding is known. Shift+Insert can read PRIMARY in some terminals, so it is not interchangeable with CLIPBOARD paste.

Clipboard contents are replaced and **not restored**. Native `desktop_type` can also replace the clipboard when an editable accessibility provider lacks direct text mutation (for example, an existing Chromium window); it verifies the destination text after that fallback. A successful paste receipt verifies the clipboard, not the receiving application. Inspect the destination, and handle any paste confirmation dialog explicitly. Do not silently switch to paste after an uncertain semantic edit; first determine what arrived.

A pasted LF can execute a terminal command immediately. Preserve the user's intended command and submission scope; never add a trailing LF as a convenience. Treat terminal bracketed/multiline-paste dialogs as real application choices, not obstacles to dismiss automatically.

## Keys and repeated navigation

```python
desktop_press_keys(window_id="<window_id>", chord="ctrl+s")
desktop_press_keys(window_id="<window_id>", chord="Down", count=5)
```

The target must be focused. Common names include `Return`, `Tab`, `Escape`, `Down`, `ctrl+plus`, `ctrl+minus`, `ctrl+equal`, `ctrl+bracketleft`, and `ctrl+slash`. Punctuation uses X11 key names; required Shift is derived from the current layout. `UNSUPPORTED_KEYMAP` refuses unavailable symbols without changing the user's mapping; use semantic tools for text.

`count` is 1–20 complete press/release chords, not a held key or automatic retry. Each iteration revalidates identity, focus, and input state. A partial/uncertain receipt may distinguish fully dispatched, possibly partial, and not-started repetitions. Inspect the caret/selection/application outcome before deciding what remains; do not replay the original count blindly.

`INPUT_HELD` means keys/buttons were already held. Let human-held input finish; do not release it yourself. Owned interrupted input has a distinct recovery procedure in [recovery](recovery.md).

## Protected fields and composition

Use `desktop_type_secret` only with an observed protected field. It replaces its contents without clipboard transport, ordinary readback, or automatic submission. Native support requires a protected EditableText provider; owned browser password fields must advertise `secret_entry_supported=true`. Unsupported providers are refused without fallback. Applications control their masking; an uncertain error can follow delivery, so never blindly repeat a password.

Ordinary text read/type refuse protected fields. Do not bypass that refusal by assuming another transport is equivalent. A deliberately requested visible digit-only OTP can use individually dispatched digit keys into an observed focused ordinary field; deliberate clearing and submission are separate steps, and key dispatch does not verify the OTP.

Native accessibility reports composition as unknown: exact text readback cannot prove pending IME preedit is absent. An enabled input method does not prove active composition, and no daemon does not prove its absence. If composition is visible or suspected, preserve it until explicitly completed/cancelled. Do not automatically press Escape/Return, change focus, or retry input to clear it. Owned-browser monitoring has stricter refusal behavior; see [optional capabilities](optional.md).
