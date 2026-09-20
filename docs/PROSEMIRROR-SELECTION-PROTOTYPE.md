# ProseMirror range-selection prototype

> Historical record from before Editor Bridge became a separate add-on. Tool names, source paths and test commands below describe the recorded revision, not the current core installation. For current setup and supported behavior, see [Editor Bridge](../addons/editor-bridge/README.md).

This is test-only evidence; production still supports whole-field replacement and end append. The candidate uses the cooperating application's actual `EditorView.domAtPos` and `posAtDOM` public APIs to map code-point endpoints into DOM positions and verify their round trip. It changes the browser Selection with a fixed `setBaseAndExtent` call, not editor DOM content or ProseMirror transactions. No caller-provided script, model setter or private view internals are used. Application initial-state/control buttons are deliberate fixture setup, and independent HTTP posts contain the real application model/DOM state.

The pinned view 1.39.2 source documents `domAtPos`/`posAtDOM` at `src/index.ts:383–422`; `src/selection.ts` shows how DOM selection changes are interpreted into model selections. Those source files were inspected locally. See the [public EditorView API](https://prosemirror.net/docs/ref/#view.EditorView.domAtPos) and [W3C Selection API](https://www.w3.org/TR/selection-api/#dom-selection-setbaseandextent). DOM endpoint equality alone does not mean ProseMirror has consumed a selection: the immediate in-script model selection was often still the old caret. The prototype waits for the actual model selection, unchanged model content and focused field before sending input. It independently checks code-point conversion, direction and UTF-16 boundaries.

Each saved mapping is tied to the actual root, document/generation and immutable model object. A same-length model change invalidates it even if a newer model could supply equally valid numeric offsets. Re-registering the same root invalidates the production field handle. The surrounding owned browser/native-window and composition guards remain in force. These checks do not make browser input atomic against application or human changes.

## Actual results

Chromium 153.0.8010.12, Playwright 1.63.0, real pinned ProseMirror basic schema/keymap, ordinary UID 1001, private Xvfb/D-Bus. Matrix suite `pm-selection-prototype` retains all failures and exits nonzero.

The expanded immutable run `run-1789890491928941683` took 18.873 seconds: **43/54 passed**, no survivors. The direct browser-native insertion route passed 19/24 rich cases; a separately labeled fresh-document delete-first route passed 21/24; ordinary HTML comparison failed all three targeted cases; three identity/focus negative checks passed. Earlier runs `run-1789890244207519107` (18/20, 7.106s) and `run-1789890339629577736` (38/40, 12.064s) remain retained. No failing operation is retried by another route in the same document.

Successful rich cases include whole astral/ZWJ selections, reversed ranges, deletion of a combining accent, ordinary middle carets, paragraph delimiter removal, multiline middle replacement, leading/trailing/empty paragraphs, and insertion/replacement across differently styled text. The candidate compares unaffected prefix and suffix characters, marks and paragraph separators after every action. It does not require adjacent text runs to retain their old serialization boundaries or claim that newly inserted text inherits a requested format.

Five direct insertion failures are material:

- Selecting only a combining accent and inserting `x` appended `x` after the whole accented grapheme.
- Selecting inside an emoji ZWJ sequence appended after the complete emoji.
- Collapsed carets inside those graphemes behaved similarly.
- Selecting a base letter while preserving its following accent replaced the complete grapheme, removing the accent outside the requested selection.

Immediately before dispatch, both DOM selection mapped back through `posAtDOM` and ProseMirror's model selection still contained the exact intended endpoints. This normalization was not observable as an already-collapsed DOM selection. Exact post-input verification correctly raised an uncertain mismatch; it did not prevent the unwanted mutation.

The three ordinary HTML comparisons reproduce the same behavior in the existing native `Input.insertText` transport: accent-only selection, interior ZWJ selection and an interior combining caret. This is not exclusively a rich-editor problem. Existing code-point offsets remain meaningful for read/selection, but native insertion does not honor every such boundary.

A separate native Backspace-then-insert route first verifies exact deletion. It fixes the two selected-substring cases, but cannot fix collapsed intra-grapheme carets or replacing a base while preserving an accent that now combines with preceding text. It is not a universal solution and is never an automatic retry. Native paragraph Enter inside a grapheme was exact in this fixture, further showing why transport-specific boundaries matter.

## Minimal production design still needed

The range mapping itself can be a read-only addition to the cooperating registry: map a validated code-point endpoint to an actual DOM node/offset, report the model position, and round-trip with `posAtDOM`. A fixed browser Selection operation can then replace the current full/end-only selection implementation, provided actual model selection catches up within a bound. Before content input, verify the saved model identity, registration, exact selected range, focus and composition again. After each native action, verify exact text, paragraph structure, caret and unaffected marks on both sides; stop on the first mismatch.

The observed browser-native failures require a refusal boundary before promising general insertion. `Intl.Segmenter` grapheme boundaries classified every direct failure's endpoints as interior to a grapheme. A narrow candidate should refuse such native-insertion requests before focus/selection/content mutation, preserve public code-point offsets, and never silently expand to a whole grapheme. This classification has not proved universal engine behavior. Deletion, Enter and clipboard paste have distinct semantics and need separately qualified routes. An explicit clipboard route may be useful but must declare its clipboard side effects and must not be attempted after possibly delivered native input.

The prototype's cancellation-independent focus case confirms that moving focus after the first insertion stops subsequent paragraphs; the delivered first segment remains. The same-length model race and renewed registration are refused before new content input. These are scoped checks, not a claim of generic ProseMirror schemas, arbitrary rich editors, full browser compatibility, or release qualification.

## Explicit clipboard comparison

A third route was selected in advance on separate fresh documents: native clipboard paste for each nonempty segment, with native Return between LF-separated segments. It does not retry a failed native insertion, set the model, or normalize spaces. Exact model text, paragraphs, caret and unaffected prefix/suffix marks are verified after every action. A bounded read-only wait allows asynchronous paste delivery; it sends no additional input.

Immutable run `run-1789891044149024905` took 29.502 seconds: **71/82 passed**, exit 1, unchanged source and no surviving owned processes. The direct route passed 20/25; delete-first passed 22/25; **clipboard passed 25/25**. The extra case covers tabs, NBSP and repeated spaces across a styled multiline selection. All eleven original native failures remain recorded (five direct, three delete-first, three ordinary HTML comparisons). Three identity/focus negatives and one clipboard side-effect assertion passed. The original baseline worktree predates the separately committed native grapheme preflight guard; its HTML failures describe that source, not the guarded production behavior.

The clipboard route preserved exact interior combining/ZWJ ranges and carets, including replacing a base character while retaining its accent. It also preserved existing strong/em marks outside the selection, paragraph boundaries, empty/trailing paragraphs, and literal whitespace. The independent application oracle recorded trusted paste events and actual model contents. For the styled-spacing case the final model retained strong `LEFT`, em `RIGHT`, and the exact inserted tab/NBSP/repeated-space text between them. Newly inserted formatting remains application-defined.

This route changes the system clipboard. A separate read of the actual X11 selection confirmed the final nonempty segment, `new`, remained there; no restoration was attempted. A future production API must make that route and retention explicit, keep native input as a distinct choice, and never switch transports automatically after a possibly delivered mutation. The evidence supports a useful cooperating-editor route, not arbitrary contenteditable editors or clipboard privacy guarantees. Native focus/content races and application paste handlers still require exact post-action checks and honest uncertain errors.
