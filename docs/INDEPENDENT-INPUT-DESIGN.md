# Independent input: implementation research and acceptance design

**Review candidate, not a default-backend release.** Chromium native keyboard
compatibility and application-issued focus remain blockers. See the
[candidate status and evidence](../tests/evidence/private-input/CANDIDATE.md).

Status: private-device routing implemented; bounded GTK/XFWM and lifecycle checks pass. Research and validation date: 2026-09-20. See [current evidence](../tests/evidence/private-input/README.md). Broader toolkit, legacy-client, and window-manager qualification remains open. GTK accessibility focus can request WM activation and redirect human focus; native device isolation does not prevent that callback. The earlier runtime at `556d699` used shared devices; its passing routing tests do not qualify independent input.

## Requirements

- Never inject into, move, release, or capture the human's input devices.
- Prefer background actions; expose windows only when the action requires it.
- Show agent activity in the existing desktop pixels, with no viewer integration.
- Keep the existing tools and automatic routing. No separate agent modes, desktop,
  Silo dependency, or replacement window manager.

Raising a window when necessary is authorized. Redirecting the human's typing or
causing an application to grab their devices is not equivalent to raising it and
does not satisfy the first requirement. Shared application content remains shared:
two keyboards cannot create independent selections or dialogs in a legacy app.

## What existing implementations establish

These are source audits, not independent qualification of the upstream products.
Pinned links allow their claims to be checked against actual implementation.

### x11vnc: independent devices and visible multi-pointer feedback

At `e2b726a8c0464051afda01648072af6835aaa5f7`, x11vnc's multi-pointer path
[creates an XI2 master pair and sets its keyboard focus](https://github.com/LibVNC/x11vnc/blob/e2b726a8c0464051afda01648072af6835aaa5f7/src/xi2_devices.c),
[injects device-specific events](https://github.com/LibVNC/x11vnc/blob/e2b726a8c0464051afda01648072af6835aaa5f7/src/xwrappers.c), and
[draws additional cursors into framebuffer pixels](https://github.com/LibVNC/x11vnc/blob/e2b726a8c0464051afda01648072af6835aaa5f7/src/cursor.c).
These are useful precedents for input ownership and ordinary viewer visibility.
Luda does not need a VNC dependency to use the underlying X11 facilities.

Its target-application ClientPointer reassignment is not safe to copy blindly:
that property belongs to an entire X client, potentially covering many windows,
and can affect simultaneous human interaction with the same application.

### MPXManager and Xorg: reuse the existing injection architecture

MPXManager `b064ba1d3c31cfd0d7cf3f8aa100ef2bb96341bf`
[binds newly opened X connections to a selected ClientPointer](https://github.com/TAAPArthur/MPXManager/blob/b064ba1d3c31cfd0d7cf3f8aa100ef2bb96341bf/src/Hacks/mpx-patch.c).
Xorg `0ea9b595891f2f31915538192961f3404d9ca699`
[routes core XTest events through PickPointer/PickKeyboard and GetXTestDevice](https://github.com/XQuartz/xorg-server/blob/0ea9b595891f2f31915538192961f3404d9ca699/Xext/xtest.c).
Therefore binding each Luda injector connection immediately after opening it can
retain the existing XTest calls while directing them to the private master pair.
This is the preferred minimal design over a second parallel injection stack.

The same binding matters for state queries and keymap initialization, not only
event emission. Xorg's
[XKB device lookup](https://github.com/XQuartz/xorg-server/blob/0ea9b595891f2f31915538192961f3404d9ca699/xkb/xkbUtils.c)
resolves the core keyboard through the requesting client's selected keyboard.
Any keyboard-map mutation must remain scoped to the agent pair; no new Unicode
remapping feature is proposed by this design.

### XFWM: independent devices do not ensure independent human focus

XFWM `d30886f7baf9088601775212ab62efac9e84795f`
[selects XI events while keeping default-seat devices](https://github.com/xfce-mirror/xfwm4/blob/d30886f7baf9088601775212ab62efac9e84795f/src/device.c)
and [uses global focus bookkeeping and core XSetInputFocus](https://github.com/xfce-mirror/xfwm4/blob/d30886f7baf9088601775212ab62efac9e84795f/src/focus.c).
This explains why the earlier private-pointer probe changed human focus. That
probe did not disprove independent device injection; it identified a WM
compatibility problem. Do not redirect the window manager's ClientPointer as a
fix: its human focus operations must continue to address human devices.

Xorg's [event implementation](https://github.com/XQuartz/xorg-server/blob/0ea9b595891f2f31915538192961f3404d9ca699/dix/events.c)
also prioritizes an existing core grab when selecting a pointer and suppresses
conflicting core events during legacy client grabs. Menus, popup lifetime, and
same-client concurrency therefore require explicit qualification. Restoring human
focus after an action is insufficient: intervening keystrokes may already be lost
or delivered to the wrong application.

### Other automation projects do not establish the complete requirement

opensymph/open-computer-use `5b433b98019c18201a15d11e8c3cb0010879a3d8`
[prefers AT-SPI actions but falls back to synthesized input](https://github.com/opensymph/open-computer-use/blob/5b433b98019c18201a15d11e8c3cb0010879a3d8/apps/OpenComputerUseLinux/atspi_node.go).
Its [native input implementation](https://github.com/opensymph/open-computer-use/blob/5b433b98019c18201a15d11e8c3cb0010879a3d8/apps/OpenComputerUseLinux/native_input.go)
calls AT-SPI registry synthesis. GNOME at-spi2-core
`b33ff15213c4c09dfc0a5b261875c65c7cffd91d`
[implements that synthesis with ordinary shared XTest input](https://github.com/GNOME/at-spi2-core/blob/b33ff15213c4c09dfc0a5b261875c65c7cffd91d/registryd/deviceeventcontroller-x11.c).
Background-operation claims alone are not evidence of independent devices.

Xpra `1533b88aedf8183798bb82c63ebaca8f1fcd91a2` is useful for
[window-pixmap capture and invalidation](https://github.com/Xpra-org/xpra/blob/1533b88aedf8183798bb82c63ebaca8f1fcd91a2/xpra/x11/composite.py),
not proof of same-desktop input isolation. Its X11 input uses shared XTest.
For covered-window observation, follow XComposite backing-pixmap lifecycle rules:
renew after resize/remap, invalidate on relevant ancestor changes, and never call
a retained unmapped pixmap a live observation. Use automatic redirection where
needed on an existing desktop, not Xpra's own-WM manual-redirection arrangement.
Observation of a covered window does not enable clicking through its covering window.

## Implementation decisions and remaining qualification

1. The implementation owns one private input pair per Luda session. Track exact device IDs,
   pair relationships, unique ownership, and server generation. Bind every Luda
   injector and cleanup connection before state queries or keymap initialization.
   Never identify owned devices by a loose name substring or reuse stale IDs.
2. Pointer, keyboard, held-state, release, crash recovery, and browser native
   focus operations bind to that pair together. Relevant existing files are `_pointer_native.py`,
   `_keyboard_native.py`, `_input_native.py`, and `_browser_input.py`. Never silently
   fall back to the human devices if private initialization or recovery fails.
3. Separate agent keyboard focus from global activation. Use device-specific
   focus; prefer raising without activation when pixels must become reachable.
   Preserve identity, geometry, coverage, popup, and stale-observation checks.
   Verify WM side effects before qualifying any route. Do not add a focus-restoring
   loop, replace the WM, or permanently reassign application ClientPointer.
4. Keep directly addressed accessibility and owned-browser operations first.
   Maintain the existing click-through overlay, tied to actual agent coordinates
   and action progress. Check for duplicate native/viewer cursor rendering.
5. Add covered-window capture only after input isolation is established. Keep it
   behind existing observation tools with explicit source/freshness metadata, so
   covered pixels cannot accidentally authorize an unsafe root-coordinate click.

The first delivery gate—device isolation plus ordinary GTK input and cleanup—has bounded passing evidence. The private pair uses `send_core=False`, which avoids the tested XFWM core-focus interference; legacy clients relying only on core events are not qualified. The second is WM/toolkit compatibility, especially grabs. If the second
gate fails, the complete user requirement remains unresolved; neither a passing
click demo nor an input-refusal-only backend counts as fully working computer use.
These sources do not establish a generic solution to every WM/grab interaction.

## Validation that distinguishes delivery from success

Use private Xvfb/XFWM sessions with an explicitly chosen account. Any shared `:1`
run must hold `/tmp/luda-live-tests.lock` for its entire lifetime. Tests should
exercise the existing public tools, not only a native helper.

- Independent application/file/DOM oracles establish the agent's actual effects.
  A separate human fixture continuously receives timestamped, identifiable typing
  and pointer actions while the agent works. Assert exact content and delivery;
  sample endpoints alone cannot detect transient focus theft.
- Record device-tagged focus/input events and human cursor position, modifiers,
  pressed buttons, and grabs. Check both separate apps and separate windows of
  the same X client; do not infer the latter from the former.
- Exercise click, hover, wheel, drag, double click, chords, text, clipboard paste,
  menus/submenus, dialogs, popup closure, and browser fallback. Include covered,
  minimized, moved, destroyed, and stale targets. Qualify GTK3, GTK4, Qt, and
  Chromium separately; unavailable providers stay unavailable in the evidence.
- Inject cancellation, timeout, owner/injector crashes, device removal, and server
  restart. Confirm only owned devices/keys/buttons are cleaned up, no physical
  device is detached, and no human modifier or button is released.
- Verify actual root-capture cursor pixels, click-through behavior, progress,
  disappearance, restart, and unchanged human cursor. A helper acknowledgement
  establishes neither visible feedback nor application success.
- For later covered capture, test compositor/no-compositor, resize, reparent,
  unmap/remap, destroy, and unavailable capture. Check image contents against an
  independent fixture and invalidate stale pixels before permitting an action.

Retain bounded evidence with runtime revision and environment. Update runtime,
schemas, documentation, skill, and diagnostic claims together when behavior ships.
Do not promote this research or the older shared-input evidence to production
qualification of independent input.
