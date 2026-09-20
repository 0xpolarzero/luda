# Editor workflows and boundaries

## Supported application contract

The developer imports `registerProseMirror(view,{paragraphs:'enter'})` from the separately shipped application module. It must run for every live view, and its returned unregister function must run when that view is retired. The bridge reads public model/selection state and maps DOM positions; it never writes model transactions or text. No automatic script injection occurs.

Accepted document shape: `doc → paragraph → text`; attribute-free `strong` and `em` marks. Optional `{paragraphs:'enter',hard_breaks:'shift-enter'}` declares an actual application Shift+Enter binding and enables attribute-free `hard_break` leaves. The application supplies the keymap and schema. Merely declaring the binding does not install it. Links, lists, tables, images, custom nodes/attributes and unsupported pending marks are refused.

A wrong declared binding can modify content before mismatch detection; the result is uncertain. This is not a general formatting or arbitrary ProseMirror-schema API.

## Example: append two paragraphs

Read the editor; obtain `characters=N`; focus it; select `(N,N)`. Call:

```json
{"element_id":"<observed>","text":"First paragraph\nSecond paragraph","mode":"insert","line_breaks":"paragraph"}
```

The sequence checks exact content, actual paragraph structure, caret and unaffected marks. A trailing LF requests a final empty paragraph. Empty segments are intentional; never trim text or replace LF with spaces.

## Example: replace a sentence within a document

Read and identify the sentence's code-point range. Focus, select `[start,end)`, then:

```json
{"element_id":"<observed>","text":"Replacement sentence.","mode":"insert","transport":"clipboard"}
```

This changes the selected sentence, preserving unaffected prefix/suffix text and marks. `mode="replace"` would replace the whole document. CLIPBOARD retains `Replacement sentence.` until another owner replaces it or the temporary browser closes. Clipboard readback cannot make delivery atomic against other clients.

Native browser input rejects boundaries inside a grapheme, such as part of a joined emoji or combining sequence. Offsets remain code points. Explicit clipboard range input has separately tested Unicode selection behavior; do not switch to it automatically after uncertain native input.

## Example: hard break inside a paragraph

Only when `supported_line_breaks` includes `hard_break`, call `editor_type` with `line_breaks="hard_break"`. The add-on sends the app's declared Shift+Enter sequence. Read logical text plus `model`/`line_break_boundaries` to distinguish this from paragraph separation. New marks follow app behavior; no formatting shortcut is inferred.

## Limits

32 registered editors, 128 paragraphs, 4,096 visited model nodes, 64,000 code points, bounded serialized model size, at most 27 input segments per call, and a six-second content sequence deadline within the outer worker watchdog. Large documents and predictable output overflow are refused before content input. Application-generated fragmentation may exceed a readback budget after input, giving an uncertain outcome.

Tokens live at most 60 seconds. Navigation, view registration replacement, window/process generation changes and display/workspace context changes invalidate observations. Old bridges may support only whole-document/end selection; inspect `selection_scope` and ask the app developer to update the adapter if arbitrary ranges are needed.

## Final receipt and retry decisions

`progress.unit="rich_text_segment"` counts requested segments, verified completed segments, at most one uncertain current segment, and untouched remainder. Empty segments can be verified without content dispatch. `application_commit_verified` remains false. Counts contain no text and are **not resume instructions**. Missing final receipts do not imply guessed progress.

After partial input, read actual content and determine a new user-intended edit. If the temporary browser was closed on timeout/cancellation, reopen only when that lifetime/loss is acceptable; a new session does not recover unsaved state or prove a previous request had no external effects.

Use `editor_close` only after the save outcome is resolved. Removing the separately installed plugin/skill/server environment leaves an independently installed core Luda unchanged.
