# Proposed minimal owned-browser adapter

Status: design for review, not implemented production support. The measured
[rich editor](OWNED-RICH-EDITOR-PROTOTYPE.md) and
[explicit cancellation](OWNED-BROWSER-CANCEL-PROTOTYPE.md) experiments justify
a useful narrow adapter, not automatic compatibility with every rich editor.

## Supported application contract

Start with two providers inside a browser launched by Luda:

1. Ordinary visible, enabled HTML text inputs and textareas. Read their native
   DOM value and selection, without cooperation from the application. Exclude
   password fields from ordinary reads and reject unsupported input types,
   cross-origin frames and shadow roots in the first version. A later secret
   entry route needs its own nonretention contract; it is not implied here.
2. ProseMirror applications that explicitly register their actual EditorView
   with a small versioned, read-only bridge. Initially accept only the basic
   document/paragraph/text schema, supported inline marks and paragraph Enter
   behavior. Reject images, custom nodes, tables, hard breaks and unknown
   schema/keymap contracts before text mutation. These exclusions are visible
   capabilities, not guesses based on a `contenteditable` attribute.

No automatic Notion, Google Docs, arbitrary Tiptap deployment, Quill, Firefox,
Electron or native GTK rich-editor support is promised. Standard HTML fields
on an ordinary website are immediately useful without a bridge. Cooperating
rich-editor support is useful to developers testing or automating their own
web apps; it is not a universal third-party website integration.

ProseMirror's supported EditorView API exposes `dom`, `state`, `composing` and
position helpers to the application that owns the view. It does not provide a
supported global discovery API for arbitrary pages. The pinned implementation
writes `dom.pmViewDesc`, but that is an internal view-description object, not
an authenticated version or supported view registry. Do not build production
compatibility by duck-typing that private property. [EditorView reference](https://prosemirror.net/docs/ref/#view.EditorView).

## Practical bridge deployment

Ship a versioned JavaScript module as a Luda integration asset, importable in
an application's normal build. An application calls, for example,
`registerProseMirror(view, {contract: 'basic-paragraphs-v1'})` after constructing
its editor and unregisters on destruction. The adapter module reads the real
view itself: model JSON, selection, stored marks, editor DOM identity and
schema/contract information. It exposes no setText or transaction-dispatch
method. The author explicitly declares that native Enter splits paragraphs;
merely detecting the ProseMirror library does not establish that behavior.

A versioned page registry returns actual registered DOM roots plus bounded
snapshots. This replaces the fixture-specific `ludaRichProbe`; it never accepts
the agent's requested text. Luda validates the root/document identity and
supported model grammar and verifies actual post-input state. The application
remains a semantic data provider, just as an accessibility provider does; the
bridge is not an attestation boundary against a dishonest application.

Do not require an unpublished npm package: initially distribute the reviewed
ES module with Luda and document bundling it locally. Publishing a separate
package can follow release ownership/versioning review. No page injection into
an existing user profile, arbitrary website extension installation or framework
monkey-patching is needed.

## Minimal public surface

Add only the following operations, retaining the existing desktop workflow:

- `desktop_open_browser(url, lifetime="temporary_session")`. For the first
  version, require the literal lifetime choice explicitly rather than hiding
  an ephemeral-browser default. Launch one fresh headed Chromium context and
  return its existing `window_id`, supported capabilities, browser version,
  `profile="temporary"` and `unsaved_content_survives_disconnect=false`.
- `desktop_cancel_composition(element_id)`, only if the explicit cancellation
  contract is accepted for production. Its description says that it sends
  Escape, may discard preedit, and can affect application UI if native
  composition already ended. It is never called implicitly to unblock typing.

Reuse `desktop_inspect`, `desktop_read_text`, `desktop_focus_element`,
`desktop_select`, `desktop_type`, `desktop_key`, screenshots and existing
window close. Inspection adds bounded `text_fields` records with ordinary
`element_id` tokens and capabilities next to the accessibility tree. Do not
merge DOM and AT-SPI fields by similar names or rectangles. Private handle
records select the correct provider; agents need no protocol or selector tool.
For an owned field, `desktop_read_text` reports representation, actual marks,
selection and composition state alongside text. Unsupported rich controls
remain inspectable through existing GUI tools without an exact-text claim.

Extend `desktop_type` with optional `line_breaks="paragraph"`. Ordinary HTML
fields retain normal LF semantics and need no new argument. Rich fields with LF
require an explicit supported interpretation; missing interpretation returns
`LINE_BREAK_SEMANTICS_REQUIRED` before input. Do not offer a hard-break route
until a real application contract and tests support it. Text insertion does
not imply a promise that all new text is bold or otherwise formatted: return
actual new formatting and preserve existing unaffected model/marks.

To keep the first rich implementation small, support full-field replace and
append at a verified collapsed end-of-document caret. Other selections or
mid-document insertion return `UNSUPPORTED_SELECTION` before mutation until
exact model/UTF-16/code-point mapping and prefix/suffix preservation are tested.
Do not silently append when the current selection requests something else.
HTML input/textarea selection can use their standard value/UTF-16 contract,
with the existing public code-point offsets and explicit conversion.

## Identity, input and verification

Each field token retains the owned browser PID/start, page target, actual
Document handle, exact ElementHandle, native-window token and provider
registration generation. Never re-resolve a selector after navigation or node
replacement. Require one unambiguous owned top-level page/native window in
version one. A popup or extra tab suspends this adapter's text route until the
binding becomes unambiguous; ordinary desktop tools still observe/control UI.
Bounds alone never establish identity. Focus uses an explicit browser-native
focus operation on the exact DOM node, followed by active-element and native
window verification; it does not click a guessed field.

Install the composition monitor before any document scripts. Unknown provenance
or active/uncertain preedit refuses text input before refocus or selection.
No automatic Escape, no guessing from committed-looking text, and no reliance
on ProseMirror's `composing` flag: the model can contain preedit and a synthetic
end can clear that flag. Explicit cancel can verify its correlated native
Escape events, but stale-active-after-commit remains postdispatch uncertainty
with possible application effects. It is not a no-effect preflight guarantee.

Use browser-native `Input.insertText` for nonempty text segments. This is a
separate owned-browser input transport, not a JavaScript value/model setter,
clipboard paste, or promise of physical key events. For the explicitly
supported paragraph contract, use native Return between segments. Before each
action revalidate identity, focus, composition, current model/selection and
operation budget. After each action independently read actual model/value,
selection and marks; stop on the first mismatch. Never retry a partially
applied operation through another transport. Results distinguish exact content,
structure, actual new formatting and preservation of unaffected content.

An initial release must test insert into existing styled prefix/suffix content,
full replacement, cancellation between segments and navigation/focus races.
The current prototype starts from fresh documents, so it is not evidence that
those production release gates are already passed. Bound field count, text,
model JSON, IPC messages, individual actions and total operation time using
existing Luda budgets; reject over-budget operations before sending text.

## Lifetime and dependencies

Use one serialized browser owner behind a bounded internal interface; keep all
Playwright objects on its owning event loop/thread and all GUI mutation under
Luda's existing operation gate. Expose fixed operations, not arbitrary eval,
CDP methods, profile paths, browser arguments or debugging endpoints. Launch
through inherited private IPC, with no public debugging port. A launch failure
must clean only its own process identities and must not close user browsers.

The smallest coherent lifetime is explicitly **temporary for this MCP session**.
Existing `desktop_close(window_id)` requests normal window closure and retains
any visible unsaved-change prompt; after confirmed closure the owner reaps its
own processes. Server shutdown/disconnect terminates this temporary owned
browser with a bounded cleanup deadline, so unsaved documents may be lost.
The required launch lifetime argument and response must make that consequence
visible. This is unsuitable for sessions expected to survive Codex reconnects.
If persistent browser work is a product requirement, review a separate managed
broker/lifecycle design first; do not quietly orphan a browser or add a daemon
in this patch. A native externally launched browser remains available through
existing desktop tools, without this exact owned-browser adapter.

Make the adapter an optional locked dependency extra, reusing the pinned
Playwright version. Default Luda installation stays unchanged. An explicit
installer option provisions the extra and a separately pinned browser artifact
(or a reviewed explicitly configured executable); record actual version/hash
in doctor. No implicit multi-hundred-megabyte download on first tool use.
Missing components report `BROWSER_ADAPTER_UNAVAILABLE` with the concrete
installation step. This proposal does not invent a published Luda or browser
artifact manifest.

## Browser-native input evidence

`rich-editor-protocol` is a test-only matrix entry. Run
`run-1789884626237200342` took 17.312 seconds, **12/14 assertions passed**, exit 1,
no survivors, unchanged source fingerprint
`0a2ddeb37a3d90ddc7e6751a700bb49cbb000c10d4aaf28fe67b0f6545d8a936`.
It verifies every segment/Return before continuing and never retries.

All nine ProseMirror paragraph payloads preserved exact text and structure,
including literal NBSP, tabs, spaces, non-BMP characters and repeated/trailing
LF. Textarea mixed trailing LF also passed. Single-line insertion with stored
bold preserved actual strong marks and emitted trusted `beforeinput`/`input`
with `inputType=insertText`, `isComposing=false`. This improves on the retained
clipboard stored-bold failure.

The multiline stored-bold expectation **failed**: text and paragraphs were
exact, but the application's native Return reset subsequent text to unmarked.
This is observed application formatting behavior, not proof that text insertion
was inexact; the original stronger probe remains failing. Generic pre-wrap
contenteditable still failed the exact serialization contract. Neither failure
is normalized away or used to claim generic rich-editor support.

The browser protocol explicitly supports inserting text independently of key
presses; [CDP Input](https://chromedevtools.github.io/devtools-protocol/tot/Input/)
and [Playwright keyboard.insertText](https://playwright.dev/docs/api/class-keyboard#keyboard-insert-text)
document that distinction. Existing X11 paste outcomes remain unchanged.
