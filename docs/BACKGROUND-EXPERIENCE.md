# Visible agent actions and automatic input routing

Luda prioritizes working computer use: background and independent input are preferred, with automatic shared foreground fallback for compatibility. The earlier [private-only candidate findings](../tests/evidence/private-input/CANDIDATE.md) remain historical evidence, not a claim that Chromium now supports private native keys.

Luda keeps the same tools and selects the input route internally. Supported
accessibility actions address the control directly. Compatible native clicks, drags, wheel input and chords use a session-owned XI2 pointer/keyboard pair. Other targets automatically receive ordinary foreground input. Device-specific focus avoids changing human focus where supported; shared fallback activates the target and may move the human pointer.

The agent indicator is rendered directly into the existing Linux X11 desktop.
Ordinary desktop viewers can display those pixels. No separate preview, Silo
integration, model credentials, or public network listener is required.

## Implementation scope

Native routing identifies the application’s AT-SPI toolkit without activating it. Positively identified GTK3 providers use independent input; unknown providers and other toolkits use foreground compatibility input. Owned-browser field operations retain directly addressed CDP input, native identity checks and DOM focus without needing independent keyboard focus. Independent devices are retired before browser startup or shared native input so applications can use the ordinary input hierarchy. Missing private-device initialization can select shared input before dispatch; an uncertain action is never replayed.

| Action | Route |
| --- | --- |
| Supported native accessibility mutations | Address the observed control directly |
| Shortcuts and clipboard paste | Choose independent or foreground input for the target and validate before input; CLIPBOARD itself remains shared |
| Screenshot clicks, hover, scrolling, and drags | Validate observed points and choose independent or shared foreground pointer input |
| Explicit window activation | Reveal the target and establish input focus for its selected route |
| Visible action feedback | Best-effort click-through cursor overlay without moving the human pointer |

The private pair disables core event emulation. This avoids the tested XFWM
legacy focus path while retaining qualified XI2-aware application input. Targets without established independent-input compatibility use shared foreground input before dispatch, rather than risking a lost action and retry. Other window managers still need separate qualification. The implementation does not guarantee that arbitrary application
callbacks cannot change shared windows, selection, dialogs, or focus. In particular,
GTK accessibility focus can call `gtk_window_present_with_time`, requesting WM
activation and redirecting human keyboard focus; private device ownership does
not prevent that application request.

Automatic routing retains stale identity, geometry, display, popup, and coverage
checks. Covered screenshot targets require revealing the intended window and
observing again. Luda neither invents coordinate clicks for unsupported semantic
actions nor retries uncertain input. No new agent mode or tool is required.
Native Wayland and Xwayland remain unsupported.

The overlay uses X11 SHAPE input regions, takes no focus, intercepts no pointer
input, and unmaps stale feedback after 1.5 seconds. It hides before pointer
validation; EOF ends the helper. Its marker means action target, not application
success. Missing rendering does not prevent otherwise valid input. Semantic
feedback uses current control geometry where available, otherwise window bounds.

## Current independent-input evidence

[Nine real MCP cases and lifecycle checks](../tests/evidence/private-input/README.md)
pass on private Xvfb/XFWM with independent GTK file oracles: actual click, wheel,
drag, key and popup effects, simultaneous human/agent typing, human-held keys and
buttons, captured cursor pixels, stale-observation refusal, same-key release
isolation, normal shutdown, and owner SIGKILL cleanup. Human keyboard focus is
sampled during each public action, not only checked at the end. This is bounded
fixture coverage, not qualification of all apps or remote viewers.

The [implementation research](INDEPENDENT-INPUT-DESIGN.md) records the pinned
upstream precedents and outstanding compatibility questions. Covered-window
capture is not added by this change.

The following older results remain as history; they do not establish the new
backend’s compatibility or noninterference.

## Historical shared-input validation

The [integrated evidence](../tests/evidence/automatic-input/README.md) records
920 passing unit tests and one optional package-build test skipped. Live tests
used private Xvfb/XFWM/D-Bus sessions; no shared desktop was controlled.

| Check | Observed result |
| --- | --- |
| Real MCP automatic routing | 12 checks passed: foreground pointer actions, background text/invoke, exact cursor pixels, moved-control feedback, disabled-control refusal, stale/covered protection and released input |
| Background native actions | 7 checks passed, including independent foreground typing while background text and button actions run |
| Existing MCP/cancellation/menu/input guards | Five suites passed; five additional pointer-guard cases passed, including injector termination and mid-wheel cancellation |
| GTK3 semantics/ranges/menus, GTK4 GUI alternatives | Passed; full scoped [native evidence](../tests/evidence/automatic-input-native/README.md) retained |
| Owned Chromium fields | 44 live checks and 8 scope checks passed, including automatic type/select foreground fallback; [browser evidence](../tests/evidence/automatic-browser/README.md) |

Qt accessibility was unavailable in this environment, and three GTK4 semantic
provider failures remained. The original runtime reproduced the same per-case
outcomes. These are limitations, not passing cases or newly qualified support.

- [`tests/test_cursor.py`](../tests/test_cursor.py): invalid coordinates, failed
  helper startup, bounded terminate/kill cleanup, and failed hide acknowledgement.
- [`tests/live_cursor.py`](../tests/live_cursor.py): actual root-capture pixels,
  unchanged focus and core pointer position, a real XTest click delivered through
  the marker to the underlying window, synchronous hide, stale auto-hide, EOF
  cleanup, and restart. This creates its own display and never uses shared `:1`.

Run from an installed development checkout:

```sh
.venv/bin/python -m unittest discover -s tests -p test_cursor.py
.venv/bin/python tests/live_cursor.py
```

No catalog case is qualified solely by these checks. The actual foreground retry
for an explicitly hidden provider is covered by unit tests; the minimized GTK
fixture can also accept direct background text, so its successful live result is
not proof that it exercised that retry.

## Earlier feasibility research

The [original research probe](../tests/prototypes/background_semantics.py) ran
before automatic routing was implemented. Four assertions established the old
public foreground refusal, background native text replacement, background button
invocation, and an application callback that opened and activated an attention
window. Independent fixture files established text and button effects; desktop
samples compared pointer position, keyboard focus, active window, and stacking.
Those samples cannot exclude brief interference between observations.

Retained [results](../tests/evidence/background-semantics/results.json) describe
that historical scope. They do not qualify arbitrary apps, minimized windows,
hidden workspaces, or concurrent human interaction. The explicitly selected root
account was a private test environment choice, not a product default.

[OpenAI's computer-use guide](https://learn.chatgpt.com/use-cases/use-your-computer-with-codex)
describes macOS background operation and a preview, but does not establish which
native APIs it uses or what equivalent Linux guarantees are possible.
[AT-SPI editable text](https://gnome.pages.gitlab.gnome.org/at-spi2-core/libatspi/method.EditableText.set_text_contents.html)
provides directly addressed mutations, while application callbacks control their
side effects. [X.Org MPX](https://www.x.org/Development/Documentation/MPX/) was
[tested](../tests/evidence/independent-input/README.md): a separate pointer still
stole foreground focus, and covered-window clicks reached the covering app.
It was therefore left out of production input routing. XComposite window capture
is also outside this implementation.
