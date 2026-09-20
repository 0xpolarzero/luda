# Cooperating ProseMirror paragraph editor

An application you own can opt into exact rich-text control by importing the shipped `luda-prosemirror.mjs` module in its normal build and registering its real `EditorView`:

```js
import {registerProseMirror} from './luda-prosemirror.mjs';
const unregister = registerProseMirror(view, {paragraphs: 'enter'});
// On editor destruction, call unregister() before view.destroy().
```

The `paragraphs: 'enter'` declaration means the application binds ordinary native Enter to splitting a paragraph, as ProseMirror's base keymap does. Only make that declaration for an editor with that behavior. The module reads the actual view; it exposes no document setters or transaction dispatch. It is an application data provider, not an attestation boundary against an application that lies. It is not an unpublished npm dependency or an automatic integration for arbitrary Tiptap/Notion/Google Docs pages.

The asset is distributed in the source tree and under `share/luda/integrations/prosemirror/` in the installed wheel. Bundle/import it normally in the application. Luda discovers registered roots only inside the fresh temporary browser that `desktop_open_browser` owns; it does not inject this integration into existing user profiles. It requires the [optional browser provider](../../docs/OWNED-BROWSER.md), with the same temporary lifetime, native-window binding, composition restrictions and cleanup behavior.

## Agent workflow

Inspect with `desktop_inspect(window_id=..., role="entry")`, then use the rich editor's `text_fields` element ID. `multiline=true` and `line_break_semantics="paragraph"` distinguish it from a textarea's literal LF value. `desktop_read_text` reports exact logical text (one LF between paragraphs), model structure, actual marks, selection and composition. Truncated text readback omits the full model rather than returning the omitted text through another property.

`desktop_type(element_id, text, mode="replace", line_breaks="paragraph")` replaces the whole editor. Default insertion is supported only at a collapsed end-of-document caret. The updated bridge supports arbitrary code-point ranges with `desktop_select`; the default native text route still refuses middle insertion. Use the explicit clipboard route below to replace those selections. A text containing LF needs explicit `line_breaks="paragraph"`; single-line text needs no extra option. Native browser text input sends each nonempty segment, and native Enter creates each requested paragraph, including empty/trailing paragraphs. No silent hard-break/paragraph substitution, clipboard normalization, DOM value assignment or model mutation occurs.

The result verifies exact text and paragraph structure after each action. Appending preserves existing prefix characters, paragraph boundaries and strong/em marks. Whole-field replacement intentionally removes old text/formatting, reported as `existing_formatting="replaced_with_field"`; append reports `"preserved"`. The returned model shows actual newly inserted formatting, which follows the application's native behavior. For example, the qualified base keymap drops stored bold on the next paragraph; Luda does not claim that all inserted paragraphs inherit bold. Application commit/autosave remains separate.

## Supported model and limits

Only `doc` → `paragraph` → `text`, without custom attributes, is supported. Existing and pending stored marks may be `strong` and `em` without attributes. This legacy paragraph declaration refuses images, hard breaks, tables, links, custom nodes/attributes and other marks before sending content. The separate hard-break declaration below narrowly extends the accepted model. The basic schema may define other nodes; their presence in the actual document is what is refused. Existing formatting outside an insertion is compared exactly, without assuming adjacent text-run boundaries remain unchanged.

Each registered view has a fresh immutable registration identity. Unregister/re-register, node replacement or navigation invalidates old handles, including re-registering the same DOM root. Limits are 32 registered editors, 128 paragraphs, 4,096 visited nodes, 64,000 code points, bounded serialized models and at most 27 input segments/53 content actions per call. Unsupported selections and over-budget requests are refused before focus/content input. The shared owner/client deadlines still apply; partial changes can remain after interruption.

Trusted composition must be known inactive before focus, selection and each input action. An untrusted composition-end event never clears real pending preedit. A conservative stale-active state can remain after Chromium commits/cancels GTK composition; there is no automatic Escape or production cancellation override. Focus, document and application state are not atomic with native dispatch. A detected mismatch or focus change after an action is uncertain, stops the sequence, and never retries through another route. Cancelling a tool may close this deliberately temporary browser; already posted application effects are not undone.

## Evidence and scope

The pinned offline fixture uses real ProseMirror model 1.25.1, view 1.39.2, state 1.4.3, commands 1.7.1, keymap 1.2.3 and basic schema 1.2.4. It imports this shipped bridge and independently posts actual model/DOM snapshots to its local application oracle. The driver uses actual public Luda MCP tools, not DOM/model setters. Test setup buttons deliberately exercise editor replacement, pending formatting and focus behavior.

Run `qualification_matrix.py --suites owned-rich --executable /absolute/chrome`. The ordinary-account private Xvfb/D-Bus run `run-1789889002865598473` passed the rich suite in 21.484 seconds and the HTML/cleanup regression in 11.262 seconds. Rich cases include all nine exact Unicode/spacing/NBSP/tab/trailing-paragraph payloads; existing bold preservation and actual later formatting; required policy, middle selection, replaced node, renewed registration, unsupported node and unsupported pending mark refusals; actual native preedit preservation; application focus change after one segment; real MCP cancellation after observed input; and explicit fresh-session recovery without replay.

Earlier failures remain in the worktree's matrix artifacts: fixture setup errors and the real empty-document AllSelection/Enter behavior. The latter is fixed by explicitly collapsing an empty replacement to its end before paragraph input. Independent review also reproduced a same-length document change during replacement selection and an unsupported pending link mark; both now refuse before content insertion, with regressions. The original generic-rich-copy, hard-break, stored-bold and composition experiments remain unchanged. That original increment did not support middle insertion. The explicit clipboard extension below is separately tested; generic rich editors, arbitrary schemas, formatting commands, native GTK and all browsers remain outside these claims.

The final focused boundary run `run-1789889287295202692` passed in 22.787 seconds. A deliberate fixture action supplied an actual 128-paragraph model, public focus/selection moved to its end, and another requested LF was refused with `VERIFICATION_LIMIT`, effect none, and the independent 128-paragraph model unchanged. This predictable output-budget overflow is checked before input. The corresponding focused unit regression also proves no focus/key dispatch.


## Explicit clipboard range replacement

After focusing the observed editor, `desktop_select(element_id, start_offset, end_offset)` selects a Unicode code-point range. The shipped bridge maps through public `EditorView.domAtPos`/`posAtDOM`; fixed DOM Selection input waits for the actual editor selection and unchanged model. It never assigns DOM text or dispatches a model transaction. Old bridge builds retain whole-field/end selection; `selection_scope` tells agents to update the cooperating application when required.

Call `desktop_type(element_id, text, transport="clipboard", line_breaks="paragraph")` to replace the selected range. The transport is explicit, accepts only cooperating basic paragraph editors, and is never tried automatically after native input. The default remains `transport="native"`. `mode="replace"` still means replace the entire editor; LF still means deliberately create paragraphs.

The clipboard route pastes each nonempty segment with browser-native Ctrl+V and sends browser-native Return between segments. These are virtual browser key events, not held X11 keys. **CLIPBOARD ends as the last nonempty segment**, until another owner replaces it or the temporary browser session closes. PRIMARY is unchanged. Empty text deliberately deletes a nonempty selection with native Backspace and does not replace CLIPBOARD; a collapsed empty request sends no text input. There is no clipboard restoration or claim that clipboard readback makes delivery atomic against other clients. Errors report whether CLIPBOARD may have changed; content can remain partially delivered.

The route checks actual model/selection/pending marks and known-inactive composition before focus and every action, then checks exact text, paragraph structure, caret and unaffected prefix **and suffix** marks after each action. Only new formatting is application-defined. Clipboard staging is independently read back before the shortcut and followed by a fresh model/focus check. Held or latched input is refused; a read-only native keyboard plan checks the current native window identity before virtual browser key dispatch. These observations cannot prevent all application/human races between checks and delivery.

The existing 64,000-code-point/128-paragraph/27-segment limits apply to the predicted final model before input, including paragraphs removed by the selected range. A six-second content deadline and outer worker watchdog remain in force. A timeout/cancellation does not undo prior input and never replays remaining segments. The worker's clipboard owner is included in the temporary session's descendant cleanup.

Initial actual public-MCP comparison passed all 25 selection/format/whitespace cases in 48.006 seconds (`run-1789891691510013797`). Expanded immutable run `run-1789891876117597843` passed 39 assertions in 53.658 seconds; the unchanged native-rich regression passed in 23.481 seconds. It included interior combining/ZWJ paste, paragraph delimiters, empty/trailing paragraphs, tabs/NBSP/repeated spaces, strong/em prefix/suffix preservation, actual held Shift and trusted native preedit refusals preserving CLIPBOARD, application focus loss after one paste, and cancellation after independent observation of `segment-0`, followed by stable partial state and explicit fresh-session recovery. Original native transport failures remain in the separately retained prototype evidence; this result does not normalize or reclassify them.


Independent fault review found a cleanup defect in the initial candidate's nested physical-key injector: stopping it after Control-down and ending the browser owner left Control held. That candidate is retained as `005c61c`; it is not the implementation to deploy. The corrected route uses CDP virtual key events plus the same read-only native target/held-state plan, so it creates no physical X11 key ownership inside the killable browser worker. A fresh-document actual-MCP run `run-1789892241143471684` passed all expanded cases in 59.881 seconds with this virtual route. The earlier native route's extra deletion/boundary run (`run-1789892126370324088`, 62.643 seconds) is also retained. Actual selected deletion inside a ZWJ sequence, combining accent and base-before-accent was exact in the cooperating ProseMirror keymap; this does not remove the separately required ordinary-HTML native deletion guard.

The final immutable runtime run `run-1789892551493165832` passed **46 assertions in 61.455 seconds**, with no surviving owned processes. This includes four explicit selected-deletion cases, stale registration, predicted paragraph overflow, clipboard retention, trusted composition and cancellation/recovery. After the read-only native plan and final clipboard verification, a fresh model/selection/pending-marks/focus check now runs immediately before virtual input; deterministic regressions prove a detected change sends no CDP input. Pre-publication storage failure preserves the old clipboard owner and reports no clipboard change; errors after publication report `clipboard_may_have_changed`, separately from verified success's `clipboard_changed`.

Final rich-input receipts can include [payload-free partial progress](../../docs/RICH-PROGRESS.md): verified segments, one uncertain current segment and untouched remainder. These counts do not prove application save or authorize automatic replay; missing final receipts do not produce guessed progress.

## Explicit hard breaks

Applications that bind native Shift+Enter to an inline `hard_break` leaf may opt in:

```js
registerProseMirror(view, {paragraphs: 'enter', hard_breaks: 'shift-enter'});
```

This registers `basic-paragraphs-hard-breaks-v1`; legacy registrations remain
paragraph-only. The module does not install the binding, change the schema, or
dispatch model transactions. The application must actually supply that behavior.
Only the existing paragraph/text model plus attribute-free `hard_break` leaves
is accepted; strong/em marks remain the only supported formatting, including on
breaks. Links, lists, images, tables, custom nodes/attributes and unsupported
pending marks remain refused before input, even when mixed with supported content.

`desktop_type(..., line_breaks="hard_break")` sends Shift+Enter between segments.
Both native whole-field/end input and explicit clipboard range replacement
support the policy. `line_breaks="paragraph"` still sends ordinary Enter.
Consecutive/empty/trailing segments create exactly those declared boundaries;
there is no automatic replacement of hard breaks by paragraphs or vice versa.

The descriptor lists `supported_line_breaks`. Logical read text uses LF for both
kinds, and `line_break_boundaries` reports their code-point offsets and actual
kinds; model JSON retains the complete structure and marks. Boundary metadata is
limited to the returned text prefix. Selection mapping uses public EditorView
DOM APIs with UTF-16 text positions and size-one hard-break nodes. Every action
verifies the exact structural sequence, caret and unaffected prefix/suffix marks.
New formatting follows the app. A wrong Shift+Enter handler can mutate the app
before mismatch detection: the result is uncertain and never retried.

The original 128-paragraph, 64,000-code-point, 4,096-node and 27-segment budgets
remain. Preflight counts mandatory paragraph/break/separated-text nodes;
application-added formatting fragmentation can still exceed a readback budget
after dispatch and cause an uncertain result. Composition, temporary lifetime,
clipboard ownership and non-atomic focus limitations are unchanged.
See [hard-break evidence](../../docs/OWNED-HARD-BREAKS.md); this is not a generic
rich-editor integration or a promise that every schema supports Shift+Enter.
