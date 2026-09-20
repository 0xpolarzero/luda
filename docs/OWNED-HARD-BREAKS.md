# Explicit cooperating ProseMirror hard breaks

The new app declaration `{paragraphs:'enter', hard_breaks:'shift-enter'}` supports
explicit `desktop_type(..., line_breaks='hard_break')`. Existing paragraph-only
apps remain unchanged. This extends the existing tool, not the supported schema
to arbitrary rich editors. The application supplies its real native binding;
Luda never writes the document model or silently normalizes line breaks.

A logical LF may represent a paragraph boundary or a hard-break leaf. Readback
reports model JSON and code-point `line_break_boundaries`; verification compares
the boundary kind after every input action. Existing text and strong/em marks
outside the changed range remain exact. App-selected formatting of new content
is reported, not forced. The read-only bridge maps actual model text UTF-16
positions and size-one break leaves through public `domAtPos`/`posAtDOM` APIs.

The pinned offline app uses ProseMirror model 1.25.1, view 1.39.2, state 1.4.3,
commands 1.7.1, keymap 1.2.3 and schema-basic 1.2.4. The actual public-MCP fixture
checks native and explicit-clipboard Unicode, combining text, emoji, tabs, NBSP,
consecutive and trailing hard breaks; mixed marked paragraphs; clipboard ranges
crossing either kind of break and middle carets; whole-field replacement;
legacy/unsupported model refusal; deliberate wrong-key binding and focus loss;
and genuine GTK simple-context pending composition refusing both transports.
Its independent app oracle records model JSON, model-derived native caret,
rendered DOM and trusted events. The driver only uses public Luda tools.

The first complete run `1789899380230596421` passed 37 records in 29.005 seconds.
Expanded run `1789899571413100054` passed 45 records in 33.276 seconds with unchanged
source and no owned survivors. Earlier setup failures are retained. A later
preflight unit tightened the mandatory-node budget to count each separated text
run, refusing a predictable 4096→4098-node request before focus or clipboard.
These are scoped results; no catalog requirement is automatically qualified.

Run the optional suite as an ordinary user on its private desktop:

```sh
.venv/bin/python scripts/qualification_matrix.py --suites owned-hard-breaks --executable /absolute/chrome
```

Native insertion still supports only whole-field replacement or end append;
arbitrary selected ranges require explicit clipboard transport. Clipboard ends
as the final nonempty segment until ownership/session changes. No fallback or
replay follows partial input. Active/unknown composition is refused; conservative
stale-active monitoring remains possible. App/native focus changes between checks
and input are non-atomic. Unknown nodes, attributes, links, custom marks and mixed
unsupported content fail before mutation rather than being flattened.

Final combined run `1789899789912478867` passed the expanded hard-break suite
(**61 records, 32.826 seconds**), legacy native paragraphs (24.405 seconds), and
legacy clipboard paragraphs (66.588 seconds). Aggregate fingerprint
`c56c14f306c56fe475c7ef62240a60eff0064e9da38b26d4ec208e12d67b2e4a` remained
unchanged and cleanup reported no owned survivors. This final suite additionally
checks rendered `<p>`/`<br>` structure, excluding ProseMirror's presentation-only
trailing placeholder, and actual trusted Shift+Enter key events. `innerText`
serialization is recorded rather than silently equated to logical model text.

Original/final logs, model oracles and source manifests are retained under
`tests/evidence/owned-hard-breaks`. Evidence/docs and two additional focused
assertions were captured after the live run; recorded runtime/fixture hashes still
match. Fifty focused rich/clipboard/progress tests pass, including prefix-bounded
boundary metadata and node-budget refusal. Actual wheel/sdist builds included the
byte-identical bridge/parser and pinned fixture, with node_modules excluded.
