# Background computer use: research and implementation target

Status: feasibility research, September 20, 2026. **Not a shipped capability.**
The prototype does not modify production input, tool schemas, or skill behavior.

## User experience to match

The agent works in the user's **existing applications**, while the user keeps
using other apps. In the user's Silo setup, the existing Linux GUI viewer is
where they watch and interact with the VM desktop. Luda's distinct agent pointer
must be visible **inside that existing desktop view**, alongside the user's own
pointer. No separate picture-in-picture preview is required. Luda must not take
over the user's pointer, keyboard focus, or foreground window. A new desktop
containing different application instances is not an equivalent implementation.

This is a standalone Linux desktop feature. Silo explains the intended viewing
experience; it does not authorize sandbox-manager integrations. A rendered cursor
indicator must survive ordinary desktop capture, rather than relying on a remote
viewer to transmit a second hardware-cursor channel.

[OpenAI's computer-use guide](https://learn.chatgpt.com/use-cases/use-your-computer-with-codex)
documents background operation on macOS and a picture-in-picture preview. It does
not document enough implementation detail to infer which native APIs it uses or
promise identical behavior on Linux. It also advises against concurrent agent
tasks in the same app.

## Current Luda gaps

| Component | Current behavior | Required work |
| --- | --- | --- |
| `desktop.py:element` | Requires an active target for native mutations | Explicit target-local background routes, with no foreground fallback |
| `_pointer_native.py` | XTEST moves the shared pointer and checks active window | Separate input routing; removing checks is insufficient |
| `desktop.py:observe` | Captures the visible desktop with scrot | Capture the target's pixels when covered, without raising it |
| `browser.py`, `_browser_worker.py` | Foreground checks; explicit `bring_to_front` on focus | Separate background behavior; current owned-browser provider is not attachment to existing signed-in browsers |
| User feedback | No distinct agent cursor rendered into desktop pixels | Click-through agent cursor/target visible in the existing GUI view, pause control, clear stale/disconnected state |

The existing pause, cancellation, identity, stale-observation, and effect-reporting
contracts must survive these changes.

## What the experiment established

[The executable research probe](../tests/prototypes/background_semantics.py)
starts two owned GTK3 fixtures in a new private Xvfb/XFWM/D-Bus session. It invokes
Luda's existing AT-SPI worker directly, intentionally bypassing only the public
foreground requirement. Independent application files establish actual effects.

Four assertions passed:

1. Public Luda refuses background text mutation with `FOCUS_CHANGED`, without
   changing the fixture text or the observed desktop state.
2. Direct AT-SPI text replacement updates the background fixture, with exact
   readback and unchanged before/after desktop state.
3. Direct AT-SPI button invocation increments the background fixture's independent
   counter, with unchanged before/after desktop state. The worker correctly
   reports dispatch, not verified button effects.
4. A different background button opens and activates an attention window through
   its application callback. **Target-local dispatch alone cannot guarantee no
   foreground interference.**

Desktop comparisons cover core pointer position, keyboard focus, active window,
and client stacking. They do not exclude transient changes between observations.
This is not qualification of concurrent human input, arbitrary toolkits, minimized
apps, hidden workspaces, screenshots, pixel input, or preview rendering. No catalog
case is marked supported by this probe.

Retained [results](../tests/evidence/background-semantics/results.json) describe
the scope. The private test ran as explicitly selected account root; this is a
test environment detail, not a product account default.

Reproduce from an installed development checkout with a private test server:

```sh
env LUDA_ISOLATED_TEST_DISPLAY=1 xvfb-run -a \
  -s '-screen 0 1440x900x24 -nolisten tcp' \
  dbus-run-session -- .venv/bin/python tests/prototypes/background_semantics.py
```

The script refuses the shared `:1` desktop. Every poll and subprocess wait is
bounded; failures raise and preserve completed assertions in the output. These
bounds are not a tested background-runtime timeout/recovery implementation.

## Linux mechanisms and limits

- **AT-SPI:** [text replacement](https://gnome.pages.gitlab.gnome.org/at-spi2-core/libatspi/method.EditableText.set_text_contents.html)
  directly addresses an editable control. This provides a useful initial route
  for supported existing apps. Application callbacks still control side effects.
  Explicit focus requests, clipboard paste, and keyboard fallback must be excluded
  from a background route unless separately proven noninterfering.
- **Multiple X11 pointers:** [X.Org MPX](https://www.x.org/Development/Documentation/MPX/)
  supports separate master pointers and keyboard focus, but documents legacy
  grabs and popup conflicts. A second cursor does not by itself guarantee
  window-manager focus preservation or correct input into covered windows.
- **Window capture:** [XComposite](https://xorg.freedesktop.org/archive/X11R7.5/doc/man/man3/Xcomposite.3.html)
  exposes redirected window storage. Capturing this instead of root pixels is a
  candidate for observing covered windows without raising them. Remapping/resizing changes storage, and
  a retained pixmap can outlive the window: identity and freshness must be checked.
  Minimized/unmapped windows cannot be assumed to keep rendering. This capture
  route has not been implemented or tested here.

## Implementation sequence

1. Define an explicit background interaction contract using existing window and
   element identities. Unsupported actions must return before input; do not
   silently activate a window or fall back to shared-pointer/keyboard input.
   Avoid a proliferation of agent-facing tools: expose mode/capability through
   existing observation and operation contracts where possible.
2. Render a separate, click-through agent cursor/target indicator directly into
   desktop pixels, visible through the existing GUI viewer, without warping the
   user's pointer or focusing the overlay. Associate the marker with the real
   target window; do not suggest that a covered foreground control is being
   clicked when the action addresses a background app. Show pending, dispatched,
   verified, failed, and stale states honestly; a semantic target marker is not
   proof of physical mouse input. Implement bounded per-window capture for agent
   observation of covered windows. Keep frames in memory by default; no public
   listener, API credentials, separate viewer, or sandbox integration.
3. Qualify direct background semantic operations first. Treat arbitrary invokes
   that may raise dialogs as an unresolved compatibility issue, not automatically
   safe actions. Checking focus afterward detects some failures; restoring focus
   afterward cannot establish that interference never happened.
4. Investigate device-specific input for missing pointer/key workflows separately.
   Test toolkit and window-manager behavior before exposing support. If universal
   routing is unattainable, disclose the actual supported app/action scope rather
   than substituting a separate desktop or claiming macOS parity.
5. Integrate runtime, MCP schemas, skill, diagnostics, installation dependencies,
   and documentation only after live evidence exists for the advertised scope.

Acceptance requires independently observed application changes alongside human
input in another app, without agent-generated movement of the human pointer or
changes to its focus and foreground. Cover occlusion, menus, modal dialogs, drags,
scrolling, typing, app exit/restart, stale identities, minimized windows, capture
loss, cancellation, timeout, and helper crashes. The visible cursor overlay must
neither steal focus nor intercept user clicks. Verify its presence in captured
desktop pixels, cleanup after exit, and held-device release. This remains an implementation project, not completed parity.
