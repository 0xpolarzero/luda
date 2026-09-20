# Visible agent actions and automatic input routing

The stricter requirement to never take over human input is not met by this
shared-input implementation. See the subsequent
[independent-input research and acceptance design](INDEPENDENT-INPUT-DESIGN.md).
That design supersedes the earlier decision to set MPX aside; it is not yet a
shipped or qualified input backend.

Luda uses its existing tools to perform actions with as little desktop interference
as the available mechanism permits. The agent does not select a background mode
or use a separate set of tools. When foreground input is needed, Luda activates
the target automatically. Application callbacks may also bring windows forward.
This is not a guarantee of uninterrupted simultaneous use or macOS feature parity.

The agent indicator is rendered directly into the existing Linux X11 desktop.
An ordinary desktop viewer can display those pixels; no separate preview, Silo
integration, model credentials, or public network listener is required.

## Implementation scope

| Action | Route |
| --- | --- |
| Supported native accessibility mutations | Address the observed control directly without activating its window or moving the shared pointer |
| Focus requests, shortcuts, clipboard paste, and foreground text input | Activate the identified target when needed, then validate before input |
| Screenshot clicks, hover, scrolling, and drags | Validate observed points, activate when needed, then revalidate before shared-pointer input |
| Visible action feedback | Best-effort click-through cursor overlay; no change to the human pointer merely to display it |

Automatic activation does not bypass stale identity, geometry, display, popup,
or coverage checks. Covered targets still require revealing the intended window
and observing again before using screenshot coordinates. Luda does not invent a
coordinate click when an accessibility operation is unsupported, or replay an
action whose effects are uncertain. Existing cancellation, pause, held-input,
and effect-reporting contracts still apply.

The cursor renderer runs in an isolated child process using X11 SHAPE input
regions. It takes no keyboard focus, intercepts no pointer input, and unmaps stale
feedback after 1.5 seconds. Luda hides it before pointer validation so the marker
does not obscure target checks. EOF ends the helper; cleanup and acknowledgement
waits are bounded. The marker indicates an action target, not application success.
A missing renderer must not prevent an otherwise valid action.
Semantic feedback uses a short, read-only lookup of current control bounds; if
geometry is unavailable, it marks the current window instead of using stale
inspection coordinates. Feedback is not a claim that the application accepted
the action.

Screenshots still capture the visible desktop. This implementation does not add
covered-window capture or independent X11 keyboard/pointer devices. Foreground
input uses the shared mouse and keyboard, and users can act between checks.
Native Wayland and Xwayland remain unsupported.

## Validation and evidence

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
