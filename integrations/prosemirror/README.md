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

`desktop_type(element_id, text, mode="replace", line_breaks="paragraph")` replaces the whole editor. Default insertion is supported only at a collapsed end-of-document caret. For supported selection, use `desktop_select` to select the whole field or collapse at its end; arbitrary middle selections are refused. A text containing LF needs explicit `line_breaks="paragraph"`; single-line text needs no extra option. Native browser text input sends each nonempty segment, and native Enter creates each requested paragraph, including empty/trailing paragraphs. No silent hard-break/paragraph substitution, clipboard normalization, DOM value assignment or model mutation occurs.

The result verifies exact text and paragraph structure after each action. Appending preserves existing prefix characters, paragraph boundaries and strong/em marks. Whole-field replacement intentionally removes old text/formatting, reported as `existing_formatting="replaced_with_field"`; append reports `"preserved"`. The returned model shows actual newly inserted formatting, which follows the application's native behavior. For example, the qualified base keymap drops stored bold on the next paragraph; Luda does not claim that all inserted paragraphs inherit bold. Application commit/autosave remains separate.

## Supported model and limits

Only `doc` → `paragraph` → `text`, without custom attributes, is supported. Existing and pending stored marks may be `strong` and `em` without attributes. Images, hard breaks, tables, links, custom nodes/attributes and other marks are refused before this route sends content. The basic schema may define other nodes; their presence in the actual document is what is refused. Existing formatting outside an appended insertion is compared exactly, without assuming adjacent text-run boundaries remain unchanged.

Each registered view has a fresh immutable registration identity. Unregister/re-register, node replacement or navigation invalidates old handles, including re-registering the same DOM root. Limits are 32 registered editors, 128 paragraphs, 4,096 visited nodes, 64,000 code points, bounded serialized models and at most 27 input segments/53 content actions per call. Unsupported selections and over-budget requests are refused before focus/content input. The shared owner/client deadlines still apply; partial changes can remain after interruption.

Trusted composition must be known inactive before focus, selection and each input action. An untrusted composition-end event never clears real pending preedit. A conservative stale-active state can remain after Chromium commits/cancels GTK composition; there is no automatic Escape or production cancellation override. Focus, document and application state are not atomic with native dispatch. A detected mismatch or focus change after an action is uncertain, stops the sequence, and never retries through another route. Cancelling a tool may close this deliberately temporary browser; already posted application effects are not undone.

## Evidence and scope

The pinned offline fixture uses real ProseMirror model 1.25.1, view 1.39.2, state 1.4.3, commands 1.7.1, keymap 1.2.3 and basic schema 1.2.4. It imports this shipped bridge and independently posts actual model/DOM snapshots to its local application oracle. The driver uses actual public Luda MCP tools, not DOM/model setters. Test setup buttons deliberately exercise editor replacement, pending formatting and focus behavior.

Run `qualification_matrix.py --suites owned-rich --executable /absolute/chrome`. The ordinary-account private Xvfb/D-Bus run `run-1789889002865598473` passed the rich suite in 21.484 seconds and the HTML/cleanup regression in 11.262 seconds. Rich cases include all nine exact Unicode/spacing/NBSP/tab/trailing-paragraph payloads; existing bold preservation and actual later formatting; required policy, middle selection, replaced node, renewed registration, unsupported node and unsupported pending mark refusals; actual native preedit preservation; application focus change after one segment; real MCP cancellation after observed input; and explicit fresh-session recovery without replay.

Earlier failures remain in the worktree's matrix artifacts: fixture setup errors and the real empty-document AllSelection/Enter behavior. The latter is fixed by explicitly collapsing an empty replacement to its end before paragraph input. Independent review also reproduced a same-length document change during replacement selection and an unsupported pending link mark; both now refuse before content insertion, with regressions. The original generic-rich-copy, hard-break, stored-bold and composition experiments remain unchanged. This bridge does not qualify generic rich editors, arbitrary schemas, middle insertion, formatting commands, native GTK or all browsers.

Packaging verification built the actual wheel and sdist and compared their bridge bytes to the tracked `.mjs`; both matched, and the parser module is included. The full branch run executed 726 tests: 725 passed and one expected integration mismatch remained because the separately maintained Silo embedded skill needed the new paragraph guidance. The eleven focused rich-provider tests pass, including fixture/bridge artifact hashes. Independent final review verified that the pending-link refusal leaves both the model and stored marks unchanged, and that same-length document replacement during selection sends no content input. All failures and earlier probes remain retained; no catalog requirement is automatically release-qualified.

The final focused boundary run `run-1789889287295202692` passed in 22.787 seconds. A deliberate fixture action supplied an actual 128-paragraph model, public focus/selection moved to its end, and another requested LF was refused with `VERIFICATION_LIMIT`, effect none, and the independent 128-paragraph model unchanged. This predictable output-budget overflow is checked before input. The corresponding focused unit regression also proves no focus/key dispatch.
