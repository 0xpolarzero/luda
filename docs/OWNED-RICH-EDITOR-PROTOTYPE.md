# Owned browser rich editor prototype

> Historical record from before Editor Bridge became a separate add-on. Tool names, source paths and test commands below describe the recorded revision, not the current core installation. For current setup and supported behavior, see [Editor Bridge](../addons/editor-bridge/README.md).

This is a test-only readback experiment, not a production browser adapter and
not qualification of WEB-03 or DATA-07. Native Luda `Desktop` methods provide
paste, keyboard input, focus and button invocation; this fixture does not test
the MCP transport. Playwright 1.63.0 launches an explicitly owned fresh headed
Chromium profile over inherited local IPC, with no debugging TCP port. No
existing user profile is attached. The ordinary-UID matrix supplies private
Xvfb, XFWM, D-Bus, XDG directories, a watchdog and owned-process cleanup.

The checked-in offline fixture pins ProseMirror model 1.25.1, view 1.39.2,
state 1.4.3, commands 1.7.1, keymap 1.2.3 and basic schema 1.2.4. Exact transitive
versions, hashes and licenses accompany the bundle. It uses a minimal real
schema/keymap configuration, not every feature of an application built with
ProseMirror. Generic contenteditable with normal/pre-wrap CSS provides a
separate comparison. No JavaScript setter inserts the requested text.

## Readback contract

The prototype retains the actual document and editor ElementHandle, browser
PID/start time and unique native-window token. It refuses replaced documents,
replaced nodes, changed content before input, ambiguous native windows, lost
focus, unknown composition-monitor provenance, pending composition and
unsupported model objects. Document identity checks do not resolve a selector
again and silently authorize its replacement. These are sequential preconditions,
not an atomic lock against a concurrent user or application mutation.

A cooperating page API reads actual ProseMirror JSON, DOM HTML, rendered
`innerText`, selection and native event metadata. Application-posted snapshots
supply a separately transported oracle of actual DOM/model state, rather than
an echo of driver arguments. Both readers necessarily trust this cooperating
fixture; they are not an attestation mechanism for arbitrary hostile pages.

The explicitly named model representation uses one LF between paragraphs and
one LF for a hard-break node. Structural JSON is retained because those two
meanings differ. Literal NBSP, tabs, Unicode and LF are compared exactly. DOM
filler, rendered blank lines and model text are separate fields. There is no
generic DOM-to-plaintext normalization and no copy serialization verifier.

## Evidence and failures

Runs are preserved under `artifacts/qualification-matrix/` in the qualification
worktree. Initial runs `run-1789882165714060502` and
`run-1789882306506978486` retain harness failures: CR input rejection was not
initially classified, and Chromium's optional command-line protocol query
requires an automation flag. Chromium also flattens its `/proc` command line;
the corrected transport check records the actual command line and inherited
Unix socket descriptors. `run-1789882353560791925` retains the first full
baseline. These were not favorable-result retries of a dispatched mutation.

The complete baseline plus separate Shift+Return attempt
`run-1789882473701688941` took 50.208 seconds on Ubuntu 24.04 ARM64,
Chromium 153.0.8010.12, UID 1001. Source fingerprint
`803bd116e0875518d3813fcc198074d7b08a5a233935f4f2b02a9617c000add3`
was unchanged. **27 of 47 assertions passed; exit status remained 1.**

Concrete outcomes:

- ProseMirror paste preserves Unicode, two model paragraphs, literal NBSP and
  tabs in some cases, but collapses some repeated/interior/trailing blank lines.
  `alpha\nbeta` becomes two model paragraphs and rendered `alpha\n\nbeta`;
  the rendered difference is recorded rather than declared equal.
- Empty model text is empty while the DOM contains a filler `<br>`.
- Generic normal/pre-wrap contenteditable has different trailing-line and
  space/NBSP behavior. It is not made equivalent to the model serializer.
- Ctrl+B before paste does not retain the expected stored bold mark. A distinct
  fresh-document paste → select-all → Ctrl+B workflow does preserve exact text,
  actual strong model marks and `<strong>` DOM markup.
- Shift+Return does not create hard-break nodes in this minimal keymap. All
  tested LF-bearing segmented hard-break attempts fail. No command binding was
  added to hide that outcome.
- Existing Luda CR rejection is an explicit unchanged-state negative contract,
  not a claim that CRLF was inserted. Empty input is a no-op.
- Replaced-node, navigation, synthetic pending-composition, unsupported-image
  and unknown-monitor-provenance guards refuse before input. The pending case
  uses an untrusted synthetic event; native IME state remains unqualified.

The separately labeled native Return route starts in fresh documents and checks
one paragraph per requested LF-separated segment, including empty/trailing
paragraphs, in addition to exact logical text. It does not reinterpret a
hard-line-break request as a paragraph request or replay a failed paste. The
first paragraph run `run-1789882773283722875` preserved all nine LF-compatible
payloads and subsequent caret insertion (37/57 overall). That run is retained
as **source_changed**, because documentation and asset tests were added while
it ran; its GUI sources were unchanged. The final immutable repeat
`run-1789882884595567845` completed in 61.771 seconds with **37/57 passing**,
all nine paragraph cases and subsequent caret insertion passing, exit 1, and
no owned-process survivors. Its unchanged source fingerprint was
`8d4f7b67998322184bd9d5409461b5628f52a4d92cbc47876fd96960b613e746`.
Only this evidence paragraph was updated after that run. The positive paragraph workflow is specifically a
paragraph-separator contract, not a generic hard-break or paste contract.

## Reproduction and scope

```sh
.venv/bin/python scripts/qualification_matrix.py --suites rich-editor-prototype \
  --executable /absolute/path/to/chromium --timeout 180
```

Run as an ordinary user with the test extra and Playwright installed in the
worktree venv. No browser download is implicit. Known failures stay nonzero.
The suite records expected synthetic payloads in test artifacts; it must not
be pointed at private user documents.

The useful improvement is representation-aware verification: the model can
separate filler from content and distinguish actual formatting from plaintext.
It does not repair transformed input. A production adapter would still need
an explicit supported-editor/representation contract, bounded offset and
selection mapping, native composition qualification, race handling and a
reviewed browser ownership lifecycle. This prototype does not expand GTK,
Firefox, Electron or arbitrary existing-browser support.

Primary references: [ProseMirror model API](https://prosemirror.net/docs/ref/#model.Node.textBetween),
[ProseMirror base keymap](https://prosemirror.net/docs/ref/#commands.baseKeymap),
[WHATWG innerText](https://html.spec.whatwg.org/multipage/dom.html#the-innertext-idl-attribute),
[Input Events](https://w3c.github.io/input-events/), and
[Playwright ElementHandle identity](https://playwright.dev/docs/api/class-elementhandle).

## Native composition follow-up

`rich-editor-ime` is a separate matrix entry using the same owned browser and
pinned model, with `GTK_IM_MODULE=simple`. A distinct monitor candidate is
installed before navigation and only accepts **trusted** composition start/end
events. The original synthetic baseline monitor is retained unchanged for
comparison. Untrusted end events cannot clear this candidate's active state.

The first actual native run `run-1789883080257517480` took 6.006 seconds and
retained exit 1 (4/6 combined assertions). Ctrl+Shift+U followed by `306b`
produced a trusted compositionstart and actual model/DOM `BASEu306b` preedit.
The input guard refused with COMPOSITION_PENDING without refocusing, selecting,
pasting or sending conflicting paragraph keys. Model, DOM, revision and
selection remained unchanged across that read-only refusal.

Separate explicit native Return committed exactly `BASEに`; native Escape
restored exactly `BASE`. The independently posted model agreed. However, in
this pinned Chromium/GTK path the observed compositionend had `isTrusted=false`
in both cases. The stricter monitor correctly ignored it and stayed active.
There was no test-injected synthetic end in these native runs. The source of
that event's trust classification has not been established. Subsequent reports
separate successful actual model completion from **failed monitor recovery**;
neither route changes its acceptance criterion to get a green result.

This exposes a production blocker: accepting every end event would let a page
clear the guard synthetically, while this conservative monitor cannot currently
prove native completion in the measured provider. Current model text alone is
not proof of committed text: the model itself temporarily contains preedit.
Unknown caller-supplied monitor provenance is refused; this test is not proof
that arbitrary late-attached pages can be reconstructed safely. No automatic
Escape, guessed composition clearing, or production adapter is introduced.

Final native run `run-1789883155727624433` took 6.048 seconds: **6/8 assertions
passed**, both monitor-recovery assertions failed, exit 1, no survivors. Source
fingerprint `b4584e9114cbdaeb3dd577db8baac95a14bd32bf1faff7d5fcc54baf5343d93e`
was unchanged during the run; this evidence paragraph and generated inventory
were updated afterward. Asset/matrix/inventory unit checks passed (20 total).

## Native end provenance comparison

Follow-up `run-1789883492944756677` records **window capture-phase** lifecycle,
input and keyboard events installed before application code, alongside
read-only `EditorView.composing`. The same native sequence was exercised in
ProseMirror, generic pre-wrap contenteditable and textarea. All three exposed
an untrusted compositionend after both native Return and Escape. No swallowed
trusted end or trusted `insertFromComposition` appeared: final input events
still used `insertCompositionText` with `isComposing=true`. Each explicit action
produced the expected actual value. This is not a ProseMirror-only artifact.

The exact browser tag provides a concrete explanation. In Chromium
153.0.8010.12, composition start/update use `EventTarget::DispatchEvent`, which
marks the event trusted. Composition end instead uses
`EventDispatcher::DispatchScopedEvent`. That queues the event without setting
trust, and its eventual dispatch bypasses the trusted setter; the event
constructor defaults to false. This source path is consistent with the direct
before-handler observation. It is not evidence that every Chromium version or
IME behaves identically. Primary source files at the exact tag:

- [InputMethodController](https://chromium.googlesource.com/chromium/src/+/refs/tags/153.0.8010.12/third_party/blink/renderer/core/editing/ime/input_method_controller.cc)
- [EventTarget dispatch](https://chromium.googlesource.com/chromium/src/+/refs/tags/153.0.8010.12/third_party/blink/renderer/core/dom/events/event_target.cc)
- [Scoped dispatch](https://chromium.googlesource.com/chromium/src/+/refs/tags/153.0.8010.12/third_party/blink/renderer/core/dom/events/event_dispatcher.cc)
- [Scoped event queue](https://chromium.googlesource.com/chromium/src/+/refs/tags/153.0.8010.12/third_party/blink/renderer/core/dom/events/scoped_event_queue.cc)
- [Event initialization](https://chromium.googlesource.com/chromium/src/+/refs/tags/153.0.8010.12/third_party/blink/renderer/core/dom/events/event.cc)

The pinned ProseMirror view 1.39.2 source handles compositionend but does not
synthesize that event. Its `composing` flag is not an authoritative substitute:
an additional fixture button arms an app-generated end event during the next
real native preedit. The button is invoked before focus and composition, so no
focus-changing input is needed while preedit is pending. The scheduled
untrusted end changes `view.composing` to false while the native preedit remains.
The trusted-only monitor stays active and refuses input; explicit later Escape
still cancels the native preedit. This demonstrates why merely consulting the
editor flag or accepting an arbitrary end event would be unsafe.

An explicit native Escape additionally produced a trusted keyup with
`isComposing=false`; native Return did not consistently expose such a keyup.
This is a candidate positive signal for a **separately authorized cancellation
recovery**, not an implemented general recovery rule. It would need event/target
identity, ordering and race qualification. No implicit cancellation, synthetic
end acceptance, or inference from current text clears the monitor here.
[UI Events](https://www.w3.org/TR/uievents/) defines composition lifecycle and
keyboard composition state; a key name by itself is not evidence of IME action.

The comparison run took 16.603 seconds, **16/22 assertions passed**, all six
monitor-recovery expectations failed, and exit 1 was preserved. Source
fingerprint `842659b9cfb52f0dd112aa0618197e5be8fb4e6f43dae3e5f98269223dfe8fcc`
was unchanged during execution and cleanup had no survivors. This report was
added afterward. Event data are retained only for synthetic test documents.
The production adapter remains unimplemented pending a sound recovery contract.
