# Browser text representation and selection

Public offsets remain Unicode code points. Chromium's legacy Text.GetSelection
currently double-converts non-BMP offsets: a correct 1..5 selection can be reported
as 1..3 even while the browser DOM selected the complete 1..5 code-point range.
The primary implementation performs conversion in both `GetSelectionExtents` and
`GetSelectionWithText` ([Chromium source](https://github.com/chromium/chromium/blob/main/ui/accessibility/platform/ax_platform_node_auralinux.cc)).

Luda uses the modern AT-SPI Document.GetTextSelections endpoint-object/range API for
Chromium instead. Both endpoint identities must match the exact observed text
object. Foreign or cross-object ranges are not guessed. `read.selection_source`
reports this path. When that API is absent, non-BMP Chromium selections are refused
rather than applying a lossy inverse conversion. SetSelection, caret and text-count
operations already use correct code-point offsets and are not reinterpreted as
UTF-16. Qt's separate provider normalization remains unchanged.

## Opaque objects are not plaintext

A multiline contenteditable can expose Text as `alpha\uFFFC\uFFFC`. Hypertext links
identify child objects, whose separate text might be `日本語 …` and `\n`. The DOM's
logical text also includes block-separating newlines absent from those Text values.
Block display attributes and visual line boundaries are not a complete serialized
plaintext contract. Luda does not silently flatten or normalize them.

Read results expose:

- `text_representation`: `plain` or `hypertext`.
- `plain_text_verification_supported`: whether plain Text comparison can verify
  this representation.
- `embedded_objects`: bounded start/end code-point offsets and child roles.
- `embedded_objects_truncated`: whether the 100-link inspection budget was reached.

Literal U+FFFC typed into a textarea is still plain text when there is no matching
Hypertext object link. Metadata therefore follows real links rather than rejecting
every occurrence of the character. Protected embedded objects are not read or
expanded. The parent must not equate opaque parent text with the full editor value.

## Evidence

`tests/live_browser_offsets.py` launches an offline headed Chromium fixture and
compares selections against independent DOM UTF-16 ranges. It covers both textarea
and simple contenteditable, multiple ranges crossing astral characters, opaque
multiline contenteditable and a literal U+FFFC textarea value. Run it under the
shared desktop lease with the optional `--executable` browser path.

The separate browser qualification suite exercises actual MCP fallback typing.
This worker regression establishes authoritative selection readback and explicit
representation limits; it does not claim full rich-editor plaintext verification.

## Focus routing and exact embedded boundaries

An accessibility focused state alone did not ensure native keyboard events reached
Chromium WebContents. The worker now attempts Component.grab_focus even when the
state already says focused. Only an unsupported request with a freshly observed
focused state retains the existing-focus result (needed for GTK4); it never
upgrades an unfocused error to success. An independent browser key/paste event
probe established the distinction.

Document selections can end at linked child-object boundaries. Exact offset zero
or the complete child length can be lifted through a bounded Hypertext link chain
into the parent's object offsets. Interior offsets and foreign objects remain
unrepresentable and are refused. This supports verifying a rich parent's selected
range without inventing a flattened plaintext representation. It does not promise
that the parent end offset is the browser's final insertion position.

## WEB-03 remains blocked: copy is not an exact general verifier

`tests/live_rich_copy.py` is a **failing qualification probe**, not a production
fallback. It uses fresh browser documents, verifies native focus, selects parent
content, installs a distinct sentinel clipboard owner, copies, requires an owner
transition, compares copied text, attempts caret restoration and checks subsequent
insertion against an independent DOM oracle.

The final fresh-document probe recorded 31 successful assertions out of 43; the
remaining 12 failures are retained and the script exits nonzero. Both AT-SPI
select-all and native Ctrl+A/Ctrl+C can omit trailing newlines. Leading/trailing
spaces can become NBSP in rich DOM, and blank-line serialization can differ between
DOM innerText and clipboard text. Parent end-offset restoration also failed for
some multiline content and could place subsequent text before an intended final
newline. A changed clipboard owner proves copy occurred; it does not prove a
lossless serialization or safe caret restoration.

No copy verification fallback is integrated. Do not trim expected newlines, map
NBSP to spaces or count these cases as qualified. Initial opaque rich text must be
refused before exact typing mutation; newly opaque output after paste requires an
explicit uncertain representation error until a correct dedicated backend exists.
