# Cooperating ProseMirror first-tool-use evaluation

On unchanged production source `0af1a742dffccec5408af120a40432d991e79475`, the
first public-MCP workflow preserved a visibly bold existing prefix, appended exact
Unicode paragraphs, explicitly saved through a native accessible button, and
matched an independent application-model/file oracle. This is one bounded
synthetic workflow, not qualification of generic rich editors.

## Evaluation discipline and limitation

Before the attempt, the evaluator read AGENTS, the shipped skill, TOOLS and the
ProseMirror integration README. No runtime implementation or existing live test
driver was read. However, an attempt to discover exports using the last 20 lines
of the pinned editor bundle unexpectedly exposed existing fixture code because
the bundle was one minified line. This was disclosed before the tool attempt.
Therefore this is **not a blind evaluation**. The app below was independently
authored using the pinned ProseMirror packages and documented registration API;
it does not import or reuse the existing fixture's setup, buttons or oracle.

The evaluator also brought prior experience with ordinary owned-browser tools.
The rich editor, paragraph policy and rich readback were first-use features here.

## Fixture and actual result

`scripts/evaluation/prosemirror-usability-app.js` initializes one paragraph with
the strong-marked text `Bold prefix: `, registers the real EditorView with
`registerProseMirror(view, {paragraphs: 'enter'})`, and binds ProseMirror's base
keymap. Initial state creation is fixture setup only. The app's Save button reads
`view.state.doc.toJSON()` and DOM paragraph/strong content, then posts it to a
loopback HTTP server, which writes the exact request bytes. No agent-task edits
use DOM/model setters, application evaluation or clipboard paste.

Run `artifacts/prosemirror-usability/1789889565222911075` used UID 1001,
private Xvfb `:0` selected by `-displayfd`, private D-Bus/XFWM, and actual
Chromium 153.0.8010.12. It never attached shared `:1`. Source, registered schemas,
bundled skill fingerprint, asset hashes and dependency versions are retained.

The public tool sequence was:

1. Doctor, open with explicit temporary-session lifetime, activate, inspect
   `role="entry"`, observe screenshot, and read the selected `text_fields` ID.
   Readback identified 13 code points and a `strong` mark on the existing prefix.
2. Focus and collapse selection at code-point offset 13. As the explicitly
   requested negative case, ask to insert `東京 😀 é\n\nFinal Ω\n` without the
   policy. It returned `LINE_BREAK_SEMANTICS_REQUIRED`, effect none, and an exact
   corrective message. A read confirmed unchanged text/model and caret 13.
   This deliberate negative case was not an accidental usability failure.
3. Make the explicit corrected request with `line_breaks="paragraph"`. It
   verified 30 code points, four paragraphs and existing formatting preservation.
   Read and observe again: `Bold prefix: 東京 😀 é` was strong, paragraph 2 was
   empty, `Final Ω` was plain text in paragraph 3, and paragraph 4 was empty.
   The screenshot corroborated visible bold versus plain text; the model and
   paragraph array established otherwise invisible trailing structure.
4. Inspect the named Save button and invoke its observed `press` action once.
   The first immediate title query returned no match; a second read-only query
   found `Synthetic document saved`. No submission input was repeated.
5. Only after this entire tool sequence, read `saved-model.json`. Its real model
   exactly matched tool readback; its DOM paragraphs were
   `["Bold prefix: 東京 😀 é", "", "Final Ω", ""]`, with only the first line
   inside `strong`. Disconnect after the independently saved file existed.

`trace.jsonl` preserves every tool request/response, including screenshot bytes,
the negative case and the initial empty title observation. `before.png` and
`after.png` are extracted tool screenshots. `metadata.json`, `schemas.json`,
`asset-manifest.json`, `saved-model.json` and `verification.json` retain source
and result evidence. A read-only verifier independently asserts those results:

```sh
.venv/bin/python scripts/evaluation/verify_prosemirror_usability.py \
  artifacts/prosemirror-usability/1789889565222911075
```

## Usability findings

The updated public skill was enough to choose the rich `text_fields` ID, append
without destroying the prefix, request paragraph semantics, and distinguish
actual formatting from plain text. The new fields-first response order,
`multiline`, `line_break_semantics` and `write_scope` directly resolved earlier
ordinary-browser inspection friction. The refusal message provided the exact
parameter correction and explicitly said no input was sent. No unexpected tool
errors or uncertain writes occurred in this attempt.

Two small documentation improvements remain concrete:

- The `desktop_inspect` generated description still says provider IDs are for
  ordinary HTML fields only; update it to include cooperating paragraph editors.
  The runtime output and skill already describe the richer capability.
- The generic `desktop_select` description says select a text range without
  noting the rich provider's whole-field/end-only constraint. Add that exception
  there, matching the integration README. The evaluator knew the constraint
  from the README and made no invalid middle-selection request.

The initial title miss is expected asynchronous application behavior, not a
failed Save. The existing guidance to verify dispatch was useful. A short example
of repeated bounded read-only observation after asynchronous save would make
that guidance more concrete without encouraging repeated submission input.

No production schemas, implementation or skill files were changed. Missing-policy
refusal was checked by tool readback, while the final saved state was checked by
an independent oracle; the fixture does not separately save a pre-refusal oracle.
This run does not test unsupported schemas, middle edits, cancellation or IME.

## Reproduction

Create the browser-extra environment from the pinned lock. Build the independent
app using the same pinned ProseMirror packages (model 1.25.1, view 1.39.2, state
1.4.3, commands 1.7.1, keymap 1.2.3 and basic schema 1.2.4) and esbuild 0.25.5.
For this evaluation guest:

```sh
mkdir -p artifacts/prosemirror-usability
NODE_PATH=/workspace/luda-rich-prototype-build-deps \
  /workspace/luda-rich-prototype-build-deps/@esbuild/linux-arm64/bin/esbuild \
  scripts/evaluation/prosemirror-usability-app.js --bundle --format=esm \
  --external:/bridge.mjs --outfile=artifacts/prosemirror-usability/app.bundle.js
chown -R desktop:desktop artifacts/prosemirror-usability
runuser -u desktop -- dbus-run-session -- \
  .venv/bin/python scripts/evaluation/prosemirror_usability.py
```

The interactive MCP client prints its new fixture URL. Send one public-tool JSON
request per line, using IDs returned by that session, and `quit` to disconnect.
The exact original requests are in the trace; session-specific IDs must be
reacquired. The harness's Chromium path is explicit and local. All generated
artifacts are ignored by the repository's existing artifacts rule.
