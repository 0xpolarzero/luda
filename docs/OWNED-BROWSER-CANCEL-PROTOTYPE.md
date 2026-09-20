# Explicit native composition cancellation prototype

This test-only extension to the [owned rich editor experiment](OWNED-RICH-EDITOR-PROTOTYPE.md)
qualifies one narrow cancellation correlation in Chromium 153.0.8010.12 on
Ubuntu 24.04 ARM64 with GTK's simple input method. It is not a production API,
a generic IME detector, automatic recovery, or a commit-text verifier.

The actual observed sequence is a trusted keydown with `code=Escape`,
`key=Process`, `isComposing=true`, followed by an untrusted compositionend and
a trusted keyup with `code=Escape`, `isComposing=false`. The exact Chromium
[KeyboardEvent implementation](https://chromium.googlesource.com/chromium/src/+/refs/tags/153.0.8010.12/third_party/blink/renderer/core/events/keyboard_event.cc)
derives the native composition flag from `InputMethodController.HasComposition()`;
the script-created constructor instead takes the supplied initializer. This
is positive native-event evidence rather than inference from current text or
the absence of an event. The [UI Events specification](https://www.w3.org/TR/uievents/)
defines keyboard composition state. This does not establish identical behavior
for other Chromium releases, input methods, browsers or desktop applications.

The candidate arms a single-use ticket before the **explicitly requested**
Escape. The ticket contains the composition generation and exact target; it
expires after 1.5 seconds. Only the matching trusted physical-code keydown/up
pair on that target can produce completion. An unrelated keydown invalidates
it. Synthetic events are ignored. A new trusted compositionstart increments
the generation and invalidates previous completion. Focus loss also invalidates
the ticket; refocusing cannot revive it. Consumption checks the generation
again and clears completion. Readback checks the retained document/node,
browser PID/start time, unique native-window token and current focus before
arming and before consuming a result. Unknown monitor provenance refuses.

The native fixture starts with `BASE`, enters real Ctrl+Shift+U `306b` preedit,
and compares actual ProseMirror state. Successful explicit cancellation restores
`BASE`; subsequent native paste produces `BASERESUMED` and the independently
posted model agrees. The suite also covers no active composition, no matching
Escape events, digit/ordinary/modifier-chord interference, synthetic Escape
keydown/keyup during real preedit, focus loss, navigation, a new composition
before consumption, ticket replay and a genuinely unmonitored fresh browser
context with active native preedit.

No-active and unknown-provenance cases send no cancellation input. A missing
correlation remains `CANCEL_UNCONFIRMED`; it is not retried. In this provider,
digit and ordinary keys are consumed by the input method without normal keyup
telemetry. The public keyboard API cannot send a standalone modifier, so the
modifier case uses Shift+A and records the events actually exposed. That chord
can itself complete composition; the candidate still refuses generic recovery.
The missing-event case withholds Escape entirely; it does not inject a native
keydown while suppressing only its release. Neither test claims broader event
coverage than observed.

## Important recovery boundary

The conservative start/end monitor can remain active after a native commit,
because that browser emits an untrusted end. Therefore `active=true` alone
cannot prove the native engine is still composing immediately before Escape.
An explicit Escape could affect application UI if composition already ended;
a subsequent uncomposed keydown would refuse cancellation confirmation only
**after dispatch**. This prototype does not promise a side-effect-free preflight.
It never sends Escape implicitly, and does not infer cancellation from text.

Correlation is not an atomic lock against another user, focus changes or browser
navigation between checks. A production design must preserve explicit user
intent, report uncertain outcomes, and review this boundary rather than present
this experiment as universally safe automatic recovery.

## Retained attempts

- `run-1789883824643534460`: initial six-case candidate passed in 10.205 seconds.
- `run-1789883953431712271`: retained harness failure: standalone `Shift_L` is
  outside the public key grammar. The corrected scenario uses supported Shift+A.
- `run-1789884005964507755`: 13/14 passed. The intended Ctrl+L focus change had
  not been observed before consumption; the fixture incorrectly treated key
  dispatch as proof of changed focus. This failed attempt remains preserved.
- `run-1789884120651211018`: actual public AX button focus plus independent
  `activeElement` readback established that precondition; 14/14 passed in
  23.938 seconds. The final variant additionally invalidates a ticket on focus
  loss and tests that refocusing cannot revive it.

Run the private ordinary-UID suite with:

```sh
.venv/bin/python scripts/qualification_matrix.py --suites rich-editor-cancel \
  --executable /absolute/path/to/chromium --timeout 90
```

No production Luda runtime, keyboard contract or installed profile is changed.

The final suite includes a separate **unsupported-recovery diagnostic**: native
Return first commits `BASEに`, leaving the conservative monitor stale-active.
A separately explicit Escape request then yields `CANCEL_UNCONFIRMED`, with
possible application effect and no retry. A passing assertion in that row means
uncertainty was preserved, not that cancellation was verified or harmless.
The fixture's text remains observable, but it does not model every application
Escape action. The prior final variant `run-1789884233121558571` passed 15/15
contracts in 24.828 seconds before this diagnostic was added.

Final immutable run `run-1789884281292463053` completed in 26.523 seconds:
**15 contract assertions plus the explicitly unsupported-recovery diagnostic
assertion passed** (16/16), no owned-process survivors. Source fingerprint
`096a8687451ad571f8793a01b17dc02c42e003ee16b65bdd6fc6d0a7311128c4`
was unchanged during execution. This evidence paragraph was added afterward.
Twenty asset/matrix/inventory unit checks passed. Earlier failures remain in
the recorded runs; the broader rich editor/native-end suites remain failing.
